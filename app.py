import streamlit as st
import requests
import pandas as pd
import json
import re
import time
import zipfile
import io
import uuid
import os

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="MysteryNarrator V19 (永不空军版)", page_icon="🛡️", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #121212; color: #e0e0e0; }
    .stButton > button { background-color: #00C853; color: white; border: none; padding: 12px; font-weight: bold; border-radius: 6px; }
    .stButton > button:hover { background-color: #009624; }
    .stSuccess { background-color: #2e7d32; color: white; }
    img { border-radius: 5px; border: 1px solid #333; }
    .debug-box { font-size: 12px; color: #888; border-left: 2px solid #555; padding-left: 10px; margin: 5px 0; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 剪映草稿生成器
# ==========================================
class JianyingDraftGenerator:
    def __init__(self):
        self.materials = {"videos": [], "audios": [], "texts": [], "canvas_animations": []}
        self.tracks = []
        self.width = 1920
        self.height = 1080
        self.us_base = 1000000 

    def _get_id(self): return str(uuid.uuid4()).upper()

    def add_media_track(self, shot_df, audio_duration_us):
        # 视频轨道
        video_segments = []
        current_offset = 0
        for i, row in shot_df.iterrows():
            material_id = self._get_id()
            duration_us = int(row['duration'] * self.us_base)
            self.materials["videos"].append({
                "id": material_id, "type": "photo", "path": f"D:/Mystery_Project/media/{i+1:03d}.jpg",
                "duration": 10800000000, "width": self.width, "height": self.height, "name": f"{i+1:03d}.jpg"
            })
            video_segments.append({
                "id": self._get_id(), "material_id": material_id,
                "target_timerange": {"duration": duration_us, "start": current_offset},
                "source_timerange": {"duration": duration_us, "start": 0}
            })
            current_offset += duration_us
        self.tracks.append({"id": self._get_id(), "type": "video", "segments": video_segments})

        # 字幕轨道
        text_segments = []
        current_offset = 0
        for i, row in shot_df.iterrows():
            duration_us = int(row['duration'] * self.us_base)
            text_id = self._get_id()
            content = {"text": str(row['script']), "styles": [{"fill": {"color": [1.0, 1.0, 1.0]}}], "strokes": [{"color": [0.0, 0.0, 0.0], "width": 0.05}]}
            self.materials["texts"].append({
                "id": text_id, "type": "text", "content": json.dumps(content), "font_size": 12.0
            })
            text_segments.append({
                "id": self._get_id(), "material_id": text_id,
                "target_timerange": {"duration": duration_us, "start": current_offset},
                "source_timerange": {"duration": duration_us, "start": 0}
            })
            current_offset += duration_us
        self.tracks.append({"id": self._get_id(), "type": "text", "segments": text_segments})

    def add_audio_track(self, audio_filename, duration_us):
        audio_id = self._get_id()
        self.materials["audios"].append({
            "id": audio_id, "path": f"D:/Mystery_Project/media/{audio_filename}",
            "duration": duration_us, "type": "extract_music", "name": audio_filename
        })
        self.tracks.append({"id": self._get_id(), "type": "audio", "segments": [{
            "id": self._get_id(), "material_id": audio_id,
            "target_timerange": {"duration": duration_us, "start": 0},
            "source_timerange": {"duration": duration_us, "start": 0}
        }]})

    def generate_json(self):
        return {"id": self._get_id(), "materials": self.materials, "tracks": self.tracks, "version": 3, "config": {"width": self.width, "height": self.height}}

# ==========================================
# 3. API 与 兜底逻辑
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}"}
def clean_json_text(text): return re.sub(r'<think>.*?</think>', '', re.sub(r'```json|```', '', text), flags=re.DOTALL).strip()

def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    files = {'file': (audio_file.name, audio_file.getvalue(), audio_file.type), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: return requests.post(url, headers=get_headers(api_key), files=files, timeout=60).json()
    except: return None

def split_long_segments(raw_segments, max_len=18):
    if not raw_segments: return []
    new_segments = []
    for seg in raw_segments:
        text = seg['text']; start = seg['start']; end = seg['end']; duration = end - start
        if len(text) > max_len:
            parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]
            part_dur = duration / len(parts)
            for i, part in enumerate(parts):
                new_segments.append({"text": part, "start": start+(i*part_dur), "end": start+((i+1)*part_dur)})
        else: new_segments.append(seg)
    return new_segments

def extract_characters_silicon(script, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    try:
        res = requests.post(url, json={"model":model,"messages":[{"role":"system","content":"提取【剧情角色】输出JSON列表:[{'name':'xx','prompt':'...'}]"},{"role":"user","content":script}],"response_format":{"type":"json_object"}}, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, timeout=30)
        df = pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])))
        if not df.empty: df = df[~df['name'].str.contains('博主|我|Host',case=False,na=False)]
        return df
    except: return pd.DataFrame(columns=['name', 'prompt'])

def analyze_segments_safe(segments, char_names, style, res_p, model, key):
    """
    带兜底机制的分镜分析。如果AI失败，自动使用默认规则生成，绝不返回空表。
    """
    if not segments:
        return pd.DataFrame(columns=['duration', 'script', 'type', 'final_prompt'])

    # 1. 尝试用 AI 分析
    try:
        input_data = json.dumps([{"id":i,"text":s['text']} for i,s in enumerate(segments)], ensure_ascii=False)
        char_list = ", ".join(char_names)
        sys_prompt = f"""
        悬疑导演。角色:{char_list}。风格:{style}。构图:{res_p}。
        任务: 为每一句字幕设计画面。Prompt: 遇角色写占位符[Name]。
        输出JSON列表 "index", "type", "final_prompt"
        """
        
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model":model,"messages":[{"role":"system","content":sys_prompt},{"role":"user","content":input_data}],"response_format":{"type":"json_object"}}, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, timeout=45)
        
        if res.status_code == 200:
            content = clean_json_text(res.json()['choices'][0]['message']['content'])
            result_list = json.loads(content)
            if isinstance(result_list, dict): result_list = result_list.get('segments', [])
            
            # 成功解析 AI 数据
            merged = []
            for i, seg in enumerate(segments):
                vis = next((item for item in result_list if item.get('index') == i), None)
                duration = seg['end'] - seg['start']
                merged.append({
                    "duration": duration, 
                    "script": seg['text'], 
                    "type": vis['type'] if vis else "SCENE", 
                    "final_prompt": vis['final_prompt'] if vis else f"Suspense scene, {style}"
                })
            return pd.DataFrame(merged)
            
    except Exception as e:
        print(f"AI Analysis Failed: {e}") # 后台打印错误，但不让前台崩
        pass 

    # 2. 【兜底机制】如果上面报错了，或者AI返回空了，执行这里
    st.warning("⚠️ AI 导演响应超时或格式错误，已切换为【自动保底模式】生成。")
    fallback_data = []
    for seg in segments:
        duration = seg['end'] - seg['start']
        # 简单的保底 Prompt
        fallback_data.append({
            "duration": duration,
            "script": seg['text'],
            "type": "SCENE",
            "final_prompt": f"Cinematic suspense shot, {style}, dark atmosphere, {res_p}"
        })
    return pd.DataFrame(fallback_data)

def inject_character_prompts(shot_df, char_df):
    if shot_df is None or shot_df.empty or 'final_prompt' not in shot_df.columns: return shot_df
    char_dict = {f"[{row['name']}]": row['prompt'] for _, row in char_df.iterrows()}
    def replace(p):
        for ph in re.findall(r'\[.*?\]', str(p)):
            if ph in char_dict: p = p.replace(ph, f"({char_dict[ph]}:1.4)")
        return p
    shot_df['final_prompt'] = shot_df['final_prompt'].apply(replace)
    return shot_df

def generate_image(prompt, size, key):
    try:
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model":"Kwai-Kolors/Kolors","prompt":prompt,"image_size":size,"batch_size":1}, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, timeout=30)
        return res.json()['data'][0]['url'] if res.status_code == 200 else "Error"
    except: return "Error"

def create_draft_zip(shot_df, imgs, audio_bytes, audio_name):
    buf = io.BytesIO()
    generator = JianyingDraftGenerator()
    total_duration_us = int(shot_df['duration'].sum() * 1000000)
    generator.add_audio_track(audio_name, total_duration_us)
    generator.add_media_track(shot_df, total_duration_us)
    
    draft_content = generator.generate_json()
    draft_meta = {"id": draft_content["id"], "name": "Mystery_Project", "last_modified": int(time.time()*1000)}

    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("draft_content.json", json.dumps(draft_content, indent=4))
        zf.writestr("draft_meta_info.json", json.dumps(draft_meta, indent=4))
        zf.writestr(f"media/{audio_name}", audio_bytes)
        for i, u in imgs.items():
            try: zf.writestr(f"media/{i+1:03d}.jpg", requests.get(u).content)
            except: pass
    return buf

# ==========================================
# 4. 界面
# ==========================================
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'gen_imgs' not in st.session_state: st.session_state.gen_imgs = {}
if 'audio_data' not in st.session_state: st.session_state.audio_data = None
if 'segments' not in st.session_state: st.session_state.segments = []

with st.sidebar:
    st.markdown("### 🔑 Key"); api_key = st.text_input("SiliconFlow Key", type="password")
    st.markdown("### 🕵️ 博主"); fixed_host = st.text_area("Prompt", "(A 30-year-old Asian man, green cap, leather jacket:1.4)", height=80)
    st.markdown("### 🛠️ 设置"); model = st.selectbox("大脑", ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"])
    res_str, res_prompt = {"16:9":("1280x720","Cinematic 16:9"), "9:16":("720x1280","9:16 portrait")}[st.selectbox("画幅", ["16:9", "9:16"])]
    style = st.text_area("风格", "Film noir, suspense thriller.", height=60)

st.title("🛡️ MysteryNarrator V19 (永不空军版)")

c1, c2 = st.columns(2)
with c1: script_input = st.text_area("1. 粘贴文案", height=150)
with c2: audio = st.file_uploader("2. 上传录音", type=['mp3','wav','m4a'])

if st.button("🔍 3. 分析"):
    if not api_key: st.error("请填 Key")
    elif not script_input or not audio: st.warning("请提供文案和录音")
    else:
        st.session_state.audio_data = {"name": audio.name, "bytes": audio.getvalue()}
        with st.spinner("双线处理中..."):
            asr = transcribe_audio(audio, api_key)
            if asr:
                segs = split_long_segments(asr.get('segments', []), max_len=18)
                st.session_state.segments = segs
                
                # 调试信息
                st.markdown(f"<div class='debug-box'>✅ 听写成功！识别到 {len(segs)} 句字幕。</div>", unsafe_allow_html=True)
                
                df = extract_characters_silicon(script_input, model, api_key)
                if df is None: df = pd.DataFrame(columns=['name', 'prompt'])
                host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                st.success(f"准备就绪")
            else:
                st.error("听写失败！API无响应，请检查录音格式或Key余额。")

if st.session_state.char_df is not None:
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed")
    if st.button("🎬 4. 生成分镜表"):
        with st.spinner("导演设计中..."):
            c_list = st.session_state.char_df['name'].tolist()
            # 使用带兜底机制的函数
            df = analyze_segments_safe(st.session_state.segments, c_list, style, res_prompt, model, api_key)
            st.session_state.shot_df = inject_character_prompts(df, st.session_state.char_df)
            st.success("OK")

if st.session_state.shot_df is not None and not st.session_state.shot_df.empty:
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, num_rows="dynamic", key="s_ed")
    
    col1, col2 = st.columns(2)
    if col1.button("🚀 5. 开始绘图"):
        bar = st.progress(0); tot = len(st.session_state.shot_df); prev = st.columns(4)
        for i, r in st.session_state.shot_df.iterrows():
            url = generate_image(r['final_prompt'], res_str, api_key)
            if "Error" not in url:
                st.session_state.gen_imgs[i] = url
                with prev[i%4]: st.image(url, caption=f"{i+1}", use_column_width=True)
            bar.progress((i+1)/tot)
            if i < tot-1: time.sleep(32)
        st.success("完成!")

    if col2.button("📦 6. 下载草稿 (JianyingDraft.zip)"):
        if st.session_state.gen_imgs:
            zip_buf = create_draft_zip(st.session_state.shot_df, st.session_state.gen_imgs, st.session_state.audio_data["bytes"], st.session_state.audio_data["name"])
            st.download_button("⬇️ 下载草稿包", zip_buf.getvalue(), "Jianying_Draft.zip", "application/zip")
        else: st.warning("请先绘图")
elif st.session_state.shot_df is not None:
    st.error("⚠️ 分镜表依然为空，请检查：录音是否静音？Key是否欠费？")
