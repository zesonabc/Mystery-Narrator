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
st.set_page_config(page_title="MysteryNarrator V34 (极速同步版)", page_icon="⚡", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #121212; color: #e0e0e0; }
    .stButton > button { background-color: #FFD600; color: black; border: none; padding: 12px; font-weight: bold; border-radius: 6px; }
    .stSuccess { background-color: #2e7d32; color: white; }
    .stError { background-color: #D32F2F; color: white; padding: 10px; border-radius: 5px; }
    img { border-radius: 5px; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 剪映草稿生成器
# ==========================================
class JianyingDraftGenerator:
    def __init__(self):
        self.project_id = str(uuid.uuid4()).upper()
        self.content_materials = {
            "videos": [], "audios": [], "texts": [], "canvas_animations": [], 
            "speeds": [], "sound_channel_mappings": []
        }
        self.tracks = []
        self.meta_materials = [] 
        self.width = 1920
        self.height = 1080
        self.us_base = 1000000 
        self.total_duration = 0 

    def _get_id(self): return str(uuid.uuid4()).upper()
    def _now(self): return int(time.time() * 1000000)

    def add_media_track(self, shot_df):
        video_segments = []
        current_offset = 0
        for i, row in shot_df.iterrows():
            material_id = self._get_id()
            duration_us = int(round(row['duration'] * self.us_base))
            file_name = f"{i+1:03d}.jpg"
            file_path = f"D:/Mystery_Project/media/{file_name}"
            
            self.content_materials["videos"].append({
                "id": material_id, "type": "photo", "path": file_path,
                "duration": 10800000000, "width": self.width, "height": self.height, "name": file_name
            })
            self.meta_materials.append({
                "create_time": self._now(), "duration": 10800000000, "extra_info": file_name, "file_Path": file_path,
                "height": self.height, "id": material_id, "import_time": self._now(), "import_time_ms": int(time.time()*1000),
                "item_source": 1, "md5": "", "metetype": "photo", "roughcut_time_range": {"duration": -1, "start": -1},
                "sub_time_range": {"duration": -1, "start": -1}, "type": 0, "width": self.width
            })
            video_segments.append({
                "id": self._get_id(), "material_id": material_id,
                "target_timerange": {"duration": duration_us, "start": current_offset},
                "source_timerange": {"duration": duration_us, "start": 0}
            })
            current_offset += duration_us
        self.tracks.append({"id": self._get_id(), "type": "video", "segments": video_segments})
        self.total_duration = max(self.total_duration, current_offset)

        text_segments = []
        current_offset = 0
        for i, row in shot_df.iterrows():
            duration_us = int(round(row['duration'] * self.us_base))
            text_id = self._get_id()
            content = {"text": str(row['script']), "styles": [{"fill": {"color": [1.0, 1.0, 1.0]}}], "strokes": [{"color": [0.0, 0.0, 0.0], "width": 0.05}]}
            self.content_materials["texts"].append({"id": text_id, "type": "text", "content": json.dumps(content), "font_size": 12.0})
            text_segments.append({
                "id": self._get_id(), "material_id": text_id,
                "target_timerange": {"duration": duration_us, "start": current_offset}, "source_timerange": {"duration": duration_us, "start": 0}})
            current_offset += duration_us
        self.tracks.append({"id": self._get_id(), "type": "text", "segments": text_segments})

    def add_audio_track(self, audio_filename, duration_us):
        audio_id = self._get_id()
        file_path = f"D:/Mystery_Project/media/{audio_filename}"
        self.content_materials["audios"].append({"id": audio_id, "path": file_path, "duration": duration_us, "type": "extract_music", "name": audio_filename})
        self.meta_materials.append({"create_time": self._now(), "duration": duration_us, "extra_info": audio_filename, "file_Path": file_path, "id": audio_id, "import_time": self._now(), "import_time_ms": int(time.time()*1000), "item_source": 1, "md5": "", "metetype": "music", "roughcut_time_range": {"duration": -1, "start": -1}, "sub_time_range": {"duration": -1, "start": -1}, "type": 1})
        self.tracks.append({"id": self._get_id(), "type": "audio", "segments": [{"id": self._get_id(), "material_id": audio_id, "target_timerange": {"duration": duration_us, "start": 0}, "source_timerange": {"duration": duration_us, "start": 0}}]})
        self.total_duration = max(self.total_duration, duration_us)

    def get_content_json(self):
        return {"id": self.project_id, "materials": self.content_materials, "tracks": self.tracks, "version": 2, "config": {"width": self.width, "height": self.height, "fps": 30}, "platform": {"os": "windows"}}

    def get_meta_json(self):
        return {"draft_materials": self.meta_materials, "tm_draft_create_time": self._now(), "tm_draft_modify_time": self._now(), "draft_root": "", "draft_cover": "", "draft_name": "Mystery_Project", "draft_id": self.project_id, "tm_duration": self.total_duration}

# ==========================================
# 3. 核心 API
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
def clean_json_text(text): return re.sub(r'<think>.*?</think>', '', re.sub(r'```json|```', '', text), flags=re.DOTALL).strip()

def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    audio_file.seek(0)
    files = {'file': (audio_file.name, audio_file.getvalue(), audio_file.type), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: return requests.post(url, headers={"Authorization": f"Bearer {api_key}"}, files=files, timeout=60).json()
    except: return None

def extract_characters_silicon(script, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    try:
        res = requests.post(url, json={"model":model,"messages":[{"role":"system","content":"提取中国悬疑剧本角色，默认中国面孔。输出JSON List: [{'name':'xx','prompt':'...'}]"},{"role":"user","content":script}],"response_format":{"type":"json_object"}}, headers=get_headers(key), timeout=45)
        df = pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])))
        if not df.empty: df = df[~df['name'].str.contains('博主|我|Host',case=False,na=False)]
        return df
    except: return pd.DataFrame(columns=['name', 'prompt'])

def analyze_segments_robust(segments, script_text, char_names, style, res_p, model, key):
    final_segments = segments if segments else []
    if not final_segments and script_text:
        chunks = re.split(r'([。？！；\n\.\?\!])', script_text)
        current = ""
        for chunk in chunks:
            if len(current) + len(chunk) < 30 and not re.match(r'[。？！\n\.\?\!]', chunk): current += chunk
            else: 
                if current.strip(): final_segments.append({"text": current, "duration": max(2.5, len(current)*0.2)})
                current = chunk
        if current.strip(): final_segments.append({"text": current, "duration": max(2.5, len(current)*0.2)})
            
    if not final_segments: return pd.DataFrame(columns=['duration', 'script', 'type', 'final_prompt'])

    try:
        char_list = ", ".join(char_names) if char_names else "无特定角色"
        input_json = json.dumps([{"id":i,"text":s.get('text','')} for i,s in enumerate(final_segments)], ensure_ascii=False)
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model":model,"messages":[{"role":"system","content":f"你是中国悬疑导演。角色:{char_list}。风格:{style}。构图:{res_p}。规则: 1. 强制中国背景(Chinese setting)，中国人(Asian Chinese face)。 2. 输出 JSON: {{'segments': [...]}}"},{"role":"user","content":input_json}],"response_format":{"type":"json_object"}}, headers=get_headers(key), timeout=90)
        result_list = json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])).get('segments', [])
        
        merged = []
        for i, seg in enumerate(final_segments):
            vis = next((item for item in result_list if item.get('index') == i), None)
            dur = seg.get('duration')
            if dur is None: dur = seg['end'] - seg['start']
            merged.append({"duration": dur, "script": seg.get('text'), "type": vis['type'] if vis else "SCENE", "final_prompt": vis['final_prompt'] if vis else f"Chinese suspense scene, {style}"})
        return pd.DataFrame(merged)
    except:
        return pd.DataFrame([{"duration": s.get('duration', max(2.5, len(s.get('text',''))*0.2)), "script": s.get('text'), "type": "SCENE", "final_prompt": f"Chinese suspense shot, {style}"} for s in final_segments])

def inject_character_prompts(shot_df, char_df):
    if shot_df is None or shot_df.empty or 'final_prompt' not in shot_df.columns: return pd.DataFrame(columns=['duration', 'script', 'type', 'final_prompt'])
    char_dict = {f"[{row['name']}]": row['prompt'] for _, row in char_df.iterrows()}
    def replace(p):
        for ph in re.findall(r'\[.*?\]', str(p)):
            if ph in char_dict: p = p.replace(ph, f"({char_dict[ph]}, Chinese face:1.4)")
        if "Chinese" not in str(p): p = f"(Chinese environment:1.3), {p}"
        return p
    shot_df['final_prompt'] = shot_df['final_prompt'].apply(replace)
    return shot_df

# 【重点修改】绘图函数：移除 time.sleep，保留超时重试
def generate_image_debug(prompt, size, key):
    max_retries = 2
    width, height = "1024", "1024" 
    if "16:9" in size: width, height = "1024", "576" 
    if "9:16" in size: width, height = "576", "1024"
    
    payload = {
        "model": "black-forest-labs/FLUX.1-schnell",
        "prompt": prompt,
        "image_size": f"{width}x{height}", 
        "batch_size": 1,
        "num_inference_steps": 4,
        "guidance_scale": 1
    }

    for attempt in range(max_retries):
        try:
            # 增加 timeout 到 120s
            res = requests.post(
                "https://api.siliconflow.cn/v1/images/generations", 
                json=payload, 
                headers=get_headers(key), 
                timeout=120 
            )
            
            if res.status_code == 200:
                return True, res.json()['images'][0]['url']
            else:
                error_msg = f"API Error {res.status_code}: {res.text}"
                # 如果失败，稍等再试
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Network Error: {str(e)}"
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            return False, error_msg

def create_draft_zip(shot_df, imgs, audio_bytes, audio_name):
    buf = io.BytesIO()
    gen = JianyingDraftGenerator()
    total_duration_us = int(shot_df['duration'].sum() * 1000000)
    gen.add_audio_track(audio_name, total_duration_us)
    gen.add_media_track(shot_df)
    
    root = "Mystery_Project_Draft"
    files = {
        "draft_content.json": json.dumps(gen.get_content_json(), indent=4),
        "draft_meta_info.json": json.dumps(gen.get_meta_json(), indent=4),
        "draft_virtual_store.json": json.dumps({"virtual_objects": []}, indent=4),
        "draft_settings": json.dumps({"draft_mode": 1, "operate_system": 1}, indent=4),
        "key_value.json": "{}",
        "draft_agency_config.json": "{}",
        "draft_biz_config.json": "{}"
    }

    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items(): zf.writestr(f"{root}/{name}", content)
        zf.writestr(f"{root}/media/{audio_name}", audio_bytes)
        
        first_img = None
        for i, u in imgs.items():
            try: 
                data = requests.get(u).content
                if i == 0: first_img = data
                zf.writestr(f"{root}/media/{i+1:03d}.jpg", data)
            except: pass
        if first_img: zf.writestr(f"{root}/draft_cover.jpg", first_img)
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
    st.markdown("### 🕵️ 博主"); fixed_host = st.text_area("Prompt", "(A 30-year-old Chinese man, Asian face, black hair, green cap, leather jacket:1.4), looking at camera", height=80)
    st.markdown("### 🧠 设置"); model = st.selectbox("大脑", ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"])
    aspect = st.selectbox("画幅", ["16:9 (横屏)", "9:16 (竖屏)"])
    style = st.text_area("风格", "Film noir, suspense thriller, Chinese background.", height=60)
    st.info("🎨 绘图: FLUX.1-schnell (极速版)")

st.title("⚡ MysteryNarrator V34 (极速同步版)")

c1, c2 = st.columns(2)
with c1: script_input = st.text_area("1. 粘贴文案", height=150)
with c2: audio = st.file_uploader("2. 上传录音", type=['mp3','wav','m4a'])

if st.button("🔍 3. 智能分析"):
    if not api_key: st.error("请填 Key")
    elif not script_input and not audio: st.error("缺输入")
    else:
        if audio:
            st.session_state.audio_data = {"name": audio.name, "bytes": audio.getvalue()}
            with st.spinner("听写..."):
                asr = transcribe_audio(audio, api_key)
                if asr and 'segments' in asr:
                    st.session_state.segments = asr['segments']
                    st.success("✅ 录音对齐成功")
                else:
                    st.session_state.segments = []
                    st.warning("⚠️ 听写失败，使用文案估算")
        else:
            st.session_state.audio_data = {"name": "silent.mp3", "bytes": b""}
            st.session_state.segments = []

        if script_input:
            df = extract_characters_silicon(script_input, model, api_key)
            host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
            st.session_state.char_df = pd.concat([host, df], ignore_index=True)
        else:
            st.session_state.char_df = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])

if st.session_state.char_df is not None:
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed", use_container_width=True)
    if st.button("🎬 4. 生成分镜"):
        with st.spinner("导演设计中..."):
            c_list = st.session_state.char_df['name'].tolist()
            safe_script = script_input if script_input else ""
            df = analyze_segments_robust(st.session_state.segments, safe_script, c_list, style, aspect, model, api_key)
            st.session_state.shot_df = inject_character_prompts(df, st.session_state.char_df)
            if st.session_state.shot_df.empty: st.error("❌ 分镜为空")
            else: st.success("OK")

if st.session_state.shot_df is not None and not st.session_state.shot_df.empty:
    st.markdown("### 5. 绘图预览")
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, num_rows="dynamic", key="s_ed", use_container_width=True)
    
    gallery_container = st.container()
    cols = gallery_container.columns(4)
    # 显示已生成的图
    if st.session_state.gen_imgs:
        for i, url in st.session_state.gen_imgs.items():
            if i < len(st.session_state.shot_df):
                with cols[i % 4]: st.image(url, caption=f"#{i+1}", use_column_width=True)

    c1, c2 = st.columns(2)
    if c1.button("🎨 5. FLUX 绘图 (极速模式)"):
        bar = st.progress(0)
        tot = len(st.session_state.shot_df)
        
        for i, r in st.session_state.shot_df.iterrows():
            success, result = generate_image_debug(r['final_prompt'], aspect, api_key)
            if success:
                st.session_state.gen_imgs[i] = result
                with cols[i % 4]: st.image(result, caption=f"#{i+1}", use_column_width=True)
            else:
                st.error(f"第 {i+1} 张失败: {result}")
            bar.progress((i+1)/tot)
            # 【优化】删除了 loop 里的 sleep，全速运行
        st.success("✅ 全部尝试完成")

    if c2.button("📦 6. 下载工程包"):
        if st.session_state.gen_imgs:
            zip_buf = create_draft_zip(st.session_state.shot_df, st.session_state.gen_imgs, st.session_state.audio_data["bytes"], st.session_state.audio_data["name"])
            st.download_button("⬇️ 下载草稿包", zip_buf.getvalue(), "Jianying_Mystery_Draft.zip", "application/zip", type="primary")
        else: st.warning("请先点击'FLUX绘图'生成图片")
