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
st.set_page_config(page_title="MysteryNarrator V25 (国风修正版)", page_icon="🇨🇳", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #121212; color: #e0e0e0; }
    .stButton > button { background-color: #B71C1C; color: white; border: none; padding: 12px; font-weight: bold; border-radius: 6px; }
    .stSuccess { background-color: #2e7d32; color: white; }
    .stWarning { background-color: #ff6f00; color: white; }
    img:hover { transform: scale(1.02); transition: 0.3s; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 剪映草稿生成器 (兼容性修复版)
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
            # 【修复】使用 round 确保四舍五入为整数，提高兼容性
            duration_us = int(round(row['duration'] * self.us_base))
            
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
            duration_us = int(round(row['duration'] * self.us_base))
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
        # 【修复】降级版本号为 2，提高老版本剪映兼容性
        return {"id": self._get_id(), "materials": self.materials, "tracks": self.tracks, "version": 2, "config": {"width": self.width, "height": self.height}}

# ==========================================
# 3. 核心 API (国风修正版)
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
def clean_json_text(text): return re.sub(r'<think>.*?</think>', '', re.sub(r'```json|```', '', text), flags=re.DOTALL).strip()

def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    audio_file.seek(0)
    files = {'file': (audio_file.name, audio_file.getvalue(), audio_file.type), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: return requests.post(url, headers={"Authorization": f"Bearer {api_key}"}, files=files, timeout=60).json()
    except: return None

# 【修复】强制中国背景的人物提取
def extract_characters_silicon(script, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    system_prompt = """
    任务：提取中国悬疑剧本中的关键角色。
    规则：
    1. 【强制】：所有角色默认必须是【中国面孔/Asian Chinese face】。
    2. 重点寻找受害者、嫌疑人。
    3. 输出 JSON List: [{'name':'王某','prompt':'A Chinese man, Asian face...'}]
    """
    try:
        res = requests.post(url, json={"model":model,"messages":[{"role":"system","content":system_prompt},{"role":"user","content":script}],"response_format":{"type":"json_object"}}, headers=get_headers(key), timeout=45)
        df = pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])))
        if not df.empty: df = df[~df['name'].str.contains('博主|我|Host',case=False,na=False)]
        return df
    except: return pd.DataFrame(columns=['name', 'prompt'])

# 【修复】智能分镜与时长计算
def analyze_segments_robust(segments, script_text, char_names, style, res_p, model, key):
    final_segments = []
    if segments:
        final_segments = segments
    else:
        # 【修复】智能计算时长：按字数 * 0.22秒，最少 2 秒
        chunks = re.split(r'([。？！；\n])', script_text)
        current = ""
        for chunk in chunks:
            if len(current) + len(chunk) < 18 and not re.match(r'[。？！\n]', chunk): current += chunk
            else: 
                if current: 
                    dur = max(2.0, len(current) * 0.22)
                    final_segments.append({"text": current, "duration": dur})
                current = chunk
        if current: 
            dur = max(2.0, len(current) * 0.22)
            final_segments.append({"text": current, "duration": dur})

    try:
        char_list = ", ".join(char_names) if char_names else "无特定角色"
        # 【修复】强制中国风的导演 Prompt
        sys_prompt = f"""
        你是中国悬疑片导演。角色:{char_list}。风格:{style}。构图:{res_p}。
        任务: 为每一句字幕设计画面 Prompt。
        【重要规则】:
        1. 【强制】：场景设定在中国(Chinese setting)，所有人物必须是中国人(Chinese Asian face)。
        2. 遇到角色写占位符[Name]。
        输出 JSON: {{"segments": [...]}}
        """
        
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model":model,"messages":[{"role":"system","content":sys_prompt},{"role":"user","content":json.dumps([{"id":i,"text":s.get('text','')} for i,s in enumerate(final_segments)], ensure_ascii=False)}],"response_format":{"type":"json_object"}}, headers=get_headers(key), timeout=90)
        result_list = json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])).get('segments', [])
        
        merged = []
        for i, seg in enumerate(final_segments):
            vis = next((item for item in result_list if item.get('index') == i), None)
            dur = seg.get('duration')
            if dur is None: dur = seg['end'] - seg['start']
            
            merged.append({
                "duration": dur,
                "script": seg.get('text'),
                "type": vis['type'] if vis else "SCENE",
                "final_prompt": vis['final_prompt'] if vis else f"Chinese suspense scene, {style}"
            })
        return pd.DataFrame(merged)

    except:
        # 兜底也用智能时长
        fallback = []
        for seg in final_segments:
            dur = seg.get('duration')
            if dur is None: dur = max(2.0, len(seg.get('text','')) * 0.22)
            fallback.append({"duration": dur, "script": seg.get('text'), "type": "SCENE", "final_prompt": f"Chinese suspense shot, {style}"})
        return pd.DataFrame(fallback)

# 【修复】强力国风注入
def inject_character_prompts(shot_df, char_df):
    if shot_df is None or shot_df.empty or 'final_prompt' not in shot_df.columns: return shot_df
    char_dict = {f"[{row['name']}]": row['prompt'] for _, row in char_df.iterrows()}
    
    def replace(p):
        # 1. 替换角色，并强制加中国特征
        for ph in re.findall(r'\[.*?\]', str(p)):
            if ph in char_dict: p = p.replace(ph, f"({char_dict[ph]}, Chinese face, Asian:1.4)")
        
        # 2. 全局强制修正：只要 Prompt 里没有 Chinese，就强制加进去
        if "Chinese" not in p and "Asian" not in p:
            p = f"(Chinese environment, Asian people:1.3), {p}"
        return p
        
    shot_df['final_prompt'] = shot_df['final_prompt'].apply(replace)
    return shot_df

def generate_image(prompt, size, key):
    try:
        width, height = 1280, 720 if "16:9" in size else 720, 1280
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model":"black-forest-labs/FLUX.1-schnell","prompt":prompt,"image_size":f"{width}x{height}","batch_size":1,"num_inference_steps":4,"guidance_scale":3.5}, headers=get_headers(key), timeout=50)
        return res.json()['images'][0]['url'] if res.status_code == 200 else "Error"
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
# 5. 界面
# ==========================================
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'gen_imgs' not in st.session_state: st.session_state.gen_imgs = {}
if 'audio_data' not in st.session_state: st.session_state.audio_data = None
if 'segments' not in st.session_state: st.session_state.segments = []

with st.sidebar:
    st.markdown("### 🔑 Key"); api_key = st.text_input("SiliconFlow Key", type="password")
    st.markdown("### 🕵️ 博主"); fixed_host = st.text_area("Prompt", "(A 30-year-old Chinese man, Asian face, black hair, green cap, leather jacket:1.4), looking at camera", height=80)
    st.markdown("### 🧠 设置"); model = st.selectbox("大脑", ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"])
    aspect = st.selectbox("画幅", ["16:9 (横屏)", "9:16 (竖屏)"])
    style = st.text_area("风格", "Film noir, suspense thriller, Chinese background, dramatic lighting.", height=60)
    st.info("🎨 绘图: FLUX.1-schnell (已强制锁定中国面孔)")

st.title("🇨🇳 MysteryNarrator V25 (国风修正版)")
st.caption("DeepSeek V3 | FLUX.1 | 剪映兼容V2")

c1, c2 = st.columns(2)
with c1: script_input = st.text_area("1. 粘贴文案", height=150)
with c2: audio = st.file_uploader("2. 上传录音", type=['mp3','wav','m4a'])

if st.button("🔍 3. 智能分析"):
    if not api_key or not script_input or not audio: st.error("缺项")
    else:
        st.session_state.audio_data = {"name": audio.name, "bytes": audio.getvalue()}
        with st.spinner("处理中..."):
            asr = transcribe_audio(audio, api_key)
            if asr and 'segments' in asr:
                st.session_state.segments = asr['segments']
                st.success(f"✅ 录音对齐成功")
            else:
                st.session_state.segments = []
                st.warning("⚠️ 使用文案智能估算时长")

            df = extract_characters_silicon(script_input, model, api_key)
            host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
            st.session_state.char_df = pd.concat([host, df], ignore_index=True)

if st.session_state.char_df is not None:
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed", use_container_width=True)
    if st.button("🎬 4. 生成分镜"):
        with st.spinner("导演设计中..."):
            c_list = st.session_state.char_df['name'].tolist()
            df = analyze_segments_robust(st.session_state.segments, script_input, c_list, style, aspect, model, api_key)
            st.session_state.shot_df = inject_character_prompts(df, st.session_state.char_df)
            st.success("OK")

if st.session_state.shot_df is not None:
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, num_rows="dynamic", key="s_ed", use_container_width=True)
    c1, c2 = st.columns(2)
    if c1.button("🎨 5. FLUX 绘图"):
        bar = st.progress(0); tot = len(st.session_state.shot_df); prev = st.columns(4)
        for i, r in st.session_state.shot_df.iterrows():
            url = generate_image(r['final_prompt'], aspect, api_key)
            if "Error" not in url:
                st.session_state.gen_imgs[i] = url
                with prev[i%4]: st.image(url, caption=f"#{i+1}", use_column_width=True)
            bar.progress((i+1)/tot); time.sleep(2)
        st.success("完成!")
    if c2.button("📦 6. 下载草稿包"):
        if st.session_state.gen_imgs:
            zip_buf = create_draft_zip(st.session_state.shot_df, st.session_state.gen_imgs, st.session_state.audio_data["bytes"], st.session_state.audio_data["name"])
            st.download_button("⬇️ 下载 ZIP", zip_buf.getvalue(), "Jianying_Mystery_Draft.zip", "application/zip", type="primary")
        else: st.warning("先绘图")
