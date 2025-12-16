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
st.set_page_config(page_title="MysteryNarrator V17 (完美草稿版)", page_icon="📦", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #121212; color: #e0e0e0; }
    .stButton > button { background-color: #00C853; color: white; border: none; padding: 12px; font-weight: bold; border-radius: 6px; }
    .stButton > button:hover { background-color: #009624; }
    .stSuccess { background-color: #2e7d32; color: white; }
    .stInfo { background-color: #0277bd; color: white; }
    img { border-radius: 5px; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 剪映草稿生成器 (JianyingPro Draft)
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
        # --- 视频轨道 (图片) ---
        video_segments = []
        current_offset = 0
        
        for i, row in shot_df.iterrows():
            material_id = self._get_id()
            # 重新计算 duration (避免浮点误差)
            duration_us = int(row['duration'] * self.us_base)
            
            self.materials["videos"].append({
                "id": material_id,
                "type": "photo",
                "path": f"D:/Mystery_Project/media/{i+1:03d}.jpg", # 虚拟路径，导入时重连
                "duration": 10800000000, 
                "width": self.width,
                "height": self.height,
                "name": f"{i+1:03d}.jpg"
            })
            
            video_segments.append({
                "id": self._get_id(),
                "material_id": material_id,
                "target_timerange": {"duration": duration_us, "start": current_offset},
                "source_timerange": {"duration": duration_us, "start": 0}
            })
            current_offset += duration_us
            
        self.tracks.append({"id": self._get_id(), "type": "video", "segments": video_segments})

        # --- 字幕轨道 (Text) ---
        text_segments = []
        current_offset = 0
        for i, row in shot_df.iterrows():
            duration_us = int(row['duration'] * self.us_base)
            text_id = self._get_id()
            
            # 字幕样式：白色字，黑色描边 (防背景干扰)
            content_obj = {
                "text": row['script'], 
                "styles": [{"fill": {"color": [1.0, 1.0, 1.0]}}],
                "strokes": [{"color": [0.0, 0.0, 0.0], "width": 0.05}] 
            }
            
            self.materials["texts"].append({
                "id": text_id,
                "type": "text",
                "content": json.dumps(content_obj),
                "font_size": 12.0 # 字体大小
            })
            
            text_segments.append({
                "id": self._get_id(),
                "material_id": text_id,
                "target_timerange": {"duration": duration_us, "start": current_offset},
                "source_timerange": {"duration": duration_us, "start": 0}
            })
            current_offset += duration_us

        self.tracks.append({"id": self._get_id(), "type": "text", "segments": text_segments})

    def add_audio_track(self, audio_filename, duration_us):
        audio_id = self._get_id()
        self.materials["audios"].append({
            "id": audio_id,
            "path": f"D:/Mystery_Project/media/{audio_filename}", # 虚拟路径
            "duration": duration_us,
            "type": "extract_music",
            "name": audio_filename
        })
        
        self.tracks.append({"id": self._get_id(), "type": "audio", "segments": [{
            "id": self._get_id(),
            "material_id": audio_id,
            "target_timerange": {"duration": duration_us, "start": 0},
            "source_timerange": {"duration": duration_us, "start": 0}
        }]})

    def generate_json(self):
        return {
            "id": self._get_id(),
            "materials": self.materials,
            "tracks": self.tracks,
            "version": 3,
            "config": {"width": self.width, "height": self.height}
        }

# ==========================================
# 3. 核心 API 函数
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}"}
def clean_json_text(text): return re.sub(r'<think>.*?</think>', '', re.sub(r'```json|```', '', text), flags=re.DOTALL).strip()

# 听写 (获取时间轴)
def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    files = {'file': (audio_file.name, audio_file.getvalue(), audio_file.type), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: return requests.post(url, headers=get_headers(api_key), files=files, timeout=60).json()
    except: return None

# 角色分析 (优先用文案分析，更准)
def extract_characters_silicon(script, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    sys_prompt = "提取文案中的【剧情角色】。输出JSON列表: [{'name':'xx','prompt':'...'}]"
    try:
        res = requests.post(url, json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":script}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=30)
        df = pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])))
        if not df.empty: df = df[~df['name'].str.contains('博主|我|Host', case=False, na=False)]
        return df
    except: return None

# 分镜设计 (使用音频的时间轴，文案的内容)
def analyze_segments(segments, char_names, style, res_p, model, key):
    input_data = json.dumps([{"id":i,"text":s['text']} for i,s in enumerate(segments)], ensure_ascii=False)
    char_list = ", ".join(char_names)
    sys_prompt = f"""
    悬疑导演。角色:{char_list}。风格:{style}。构图:{res_p}。
    任务: 为每一句字幕设计画面。Prompt: 遇角色写占位符[Name]。
    输出JSON列表 "index", "type", "final_prompt"
    """
    try:
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model":model,"messages":[{"role":"system","content":sys_prompt},{"role":"user","content":input_data}],"response_format":{"type":"json_object"}}, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, timeout=60)
        result_list = json.loads(clean_json_text(res.json()['choices'][0]['message']['content']))
        if isinstance(result_list, dict): result_list = result_list.get('segments', [])
        
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
    except: return None

# 角色注入 (锁脸)
def inject_character_prompts(shot_df, char_df):
    if shot_df is None or char_df is None: return shot_df
    char_dict = {f"[{row['name']}]": row['prompt'] for _, row in char_df.iterrows()}
    def replace(p):
        for ph in re.findall(r'\[.*?\]', p):
            if ph in char_dict: p = p.replace(ph, f"({char_dict[ph]}:1.4)")
        return p
    shot_df['final_prompt'] = shot_df['final_prompt'].apply(replace)
    return shot_df

# 画图
def generate_image(prompt, size, key):
    try:
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model":"Kwai-Kolors/Kolors","prompt":prompt,"image_size":size,"batch_size":1}, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, timeout=30)
        return res.json()['data'][0]['url'] if res.status_code == 200 else "Error"
    except: return "Error"

# 强制切分 (处理长难句)
def split_long_segments(raw_segments, max_len=18):
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

# ==========================================
# 4. 打包功能
# ==========================================
def create_draft_zip(shot_df, imgs, audio_bytes, audio_name):
    buf = io.BytesIO()
    generator = JianyingDraftGenerator()
    total_duration_us = int(shot_df['duration'].sum() * 1000000)
    
    # 构建草稿结构
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
# 5. 界面 UI
# ==========================================
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'gen_imgs' not in st.session_state: st.session_state.gen_imgs = {}
if 'audio_data' not in st.session_state: st.session_state.audio_data = None
if 'segments' not in st.session_state: st.session_state.segments = []

with st.sidebar:
    st.markdown("### 🔑 API Key"); api_key = st.text_input("SiliconFlow Key", type="password")
    st.markdown("### 🕵️ 博主形象"); fixed_host = st.text_area("Prompt", "(A 30-year-old Asian man, green cap, leather jacket:1.4)", height=80)
    st.markdown("### 🛠️ 设置"); model = st.selectbox("大脑", ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"])
    res_str, res_prompt = {"16:9":("1280x720","Cinematic 16:9"), "9:16":("720x1280","9:16 portrait")}[st.selectbox("画幅", ["16:9", "9:16"])]
    style = st.text_area("风格", "Film noir, suspense thriller.", height=60)

st.title("📦 MysteryNarrator V17 (完美草稿版)")
st.caption("逻辑修正：先文案分析角色 -> 后录音对齐时间 -> 导出剪映草稿")

# --- Step 1: 文案与录音 ---
c1, c2 = st.columns(2)
with c1:
    script_input = st.text_area("1. 粘贴文案 (用于精准分析角色)", height=150)
with c2:
    audio = st.file_uploader("2. 上传录音 (用于对齐时间)", type=['mp3','wav','m4a'])

if st.button("🔍 3. 分析文案 & 听写对齐"):
    if not api_key: st.error("请填 Key")
    elif not script_input or not audio: st.warning("请同时提供文案和录音")
    else:
        st.session_state.audio_data = {"name": audio.name, "bytes": audio.getvalue()}
        
        # 并行处理：文案分析角色 + 录音分析时间
        with st.spinner("双线处理中：分析角色 + 语音对齐..."):
            # 1. 听写 (获取时间轴)
            asr = transcribe_audio(audio, api_key)
            if asr:
                # 强制切分长句 (保证字幕短)
                st.session_state.segments = split_long_segments(asr.get('segments', []), max_len=18)
                
                # 2. 角色提取 (用左边的纯文案，更准)
                df = extract_characters_silicon(script_input, model, api_key)
                if df is not None:
                    host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                    st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                    st.success(f"分析完成！共 {len(st.session_state.segments)} 个分镜。")

# --- Step 2: 确认 ---
if st.session_state.char_df is not None:
    st.markdown("---")
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed")
    
    if st.button("🎬 4. 生成分镜表"):
        with st.spinner("导演设计中..."):
            c_list = st.session_state.char_df['name'].tolist()
            # 用听写出来的 segments (带时间) + 角色表 + 风格
            df = analyze_segments(st.session_state.segments, c_list, style, res_prompt, model, api_key)
            if df is not None:
                st.session_state.shot_df = inject_character_prompts(df, st.session_state.char_df)
                st.success("分镜已生成")

# --- Step 3: 绘图与导出 ---
if st.session_state.shot_df is not None:
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, num_rows="dynamic", key="s_ed")
    
    col_a, col_b = st.columns(2)
    if col_a.button("🚀 5. 开始绘图"):
        bar = st.progress(0); tot = len(st.session_state.shot_df); prev = st.columns(4)
        for i, r in st.session_state.shot_df.iterrows():
            url = generate_image(r['final_prompt'], res_str, api_key)
            if "Error" not in url:
                st.session_state.gen_imgs[i] = url
                with prev[i%4]: st.image(url, caption=f"{i+1}", use_column_width=True)
            bar.progress((i+1)/tot)
            if i < tot-1: time.sleep(32)
        st.success("绘图完成!")

    if col_b.button("📦 6. 下载草稿包 (JianyingDraft.zip)"):
        if st.session_state.gen_imgs:
            zip_buf = create_draft_zip(
                st.session_state.shot_df, 
                st.session_state.gen_imgs, 
                st.session_state.audio_data["bytes"],
                st.session_state.audio_data["name"]
            )
            st.download_button("⬇️ 下载工程包", zip_buf.getvalue(), "Jianying_Draft.zip", "application/zip")
        else: st.warning("请先绘图")
