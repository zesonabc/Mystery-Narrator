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
st.set_page_config(page_title="MysteryNarrator V26 (工程修复版)", page_icon="🛠️", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #121212; color: #e0e0e0; }
    .stButton > button { background-color: #FF5252; color: white; border: none; padding: 12px; font-weight: bold; border-radius: 6px; }
    .stSuccess { background-color: #2e7d32; color: white; }
    img:hover { transform: scale(1.02); transition: 0.3s; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 剪映草稿生成器 (结构深度优化)
# ==========================================
class JianyingDraftGenerator:
    def __init__(self):
        self.materials = {"videos": [], "audios": [], "texts": [], "canvas_animations": [], "speeds": [], "sound_channel_mappings": []}
        self.tracks = []
        self.width = 1920
        self.height = 1080
        self.us_base = 1000000 

    def _get_id(self): return str(uuid.uuid4()).upper()

    def add_media_track(self, shot_df, audio_duration_us):
        # 1. 视频轨道 (Images)
        video_segments = []
        current_offset = 0
        for i, row in shot_df.iterrows():
            material_id = self._get_id()
            # 强制整数时长
            duration_us = int(round(row['duration'] * self.us_base))
            
            self.materials["videos"].append({
                "id": material_id, 
                "type": "photo", 
                "path": f"D:/Mystery_Project/media/{i+1:03d}.jpg", # 虚拟路径
                "duration": 10800000000, # 图片素材默认长度给大一点
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

        # 2. 字幕轨道 (Texts)
        text_segments = []
        current_offset = 0
        for i, row in shot_df.iterrows():
            duration_us = int(round(row['duration'] * self.us_base))
            text_id = self._get_id()
            
            # 样式：白字黑边
            content = {
                "text": str(row['script']), 
                "styles": [{"fill": {"color": [1.0, 1.0, 1.0]}}], 
                "strokes": [{"color": [0.0, 0.0, 0.0], "width": 0.05}]
            }
            
            self.materials["texts"].append({
                "id": text_id, 
                "type": "text", 
                "content": json.dumps(content), 
                "font_size": 12.0
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
            "path": f"D:/Mystery_Project/media/{audio_filename}", 
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
        # 增加一些空列表以匹配标准格式，防止加载卡死
        return {
            "id": self._get_id(), 
            "materials": self.materials, 
            "tracks": self.tracks, 
            "version": 2, 
            "config": {"width": self.width, "height": self.height},
            "platform": {"os": "windows"}
        }

# ==========================================
# 3. 核心 API (修复 KeyError)
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
    sys_prompt = "提取中国悬疑剧本角色。规则：1. 默认中国面孔(Asian Chinese)。2. 输出JSON List: [{'name':'xx','prompt':'...'}]"
    try:
        res = requests.post(url, json={"model":model,"messages":[{"role":"system","content":sys_prompt},{"role":"user","content":script}],"response_format":{"type":"json_object"}}, headers=get_headers(key), timeout=45)
        df = pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])))
        if not df.empty: df = df[~df['name'].str.contains('博主|我|Host',case=False,na=False)]
        return df
    except: return pd.DataFrame(columns=['name', 'prompt']) # 返回带列名的空表

def analyze_segments_robust(segments, script_text, char_names, style, res_p, model, key):
    final_segments = []
    
    # 1. 数据源准备
    if segments:
        final_segments = segments
    elif script_text and len(script_text.strip()) > 0:
        # B计划：文案不为空，进行切分
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
    
    # 【修复核心】如果到这里 final_segments 还是空的，直接返回一个标准的空 DataFrame
    # 必须包含所有后续步骤需要的列名！
    if not final_segments:
        return pd.DataFrame(columns=['duration', 'script', 'type', 'final_prompt'])

    try:
        # 2. AI 分析
        char_list = ", ".join(char_names) if char_names else "无特定角色"
        sys_prompt = f"""
        你是中国悬疑导演。角色:{char_list}。风格:{style}。构图:{res_p}。
        任务: 为每一句字幕设计画面 Prompt。
        规则:
        1. 强制中国背景(Chinese setting)，中国人(Asian Chinese face)。
        2. 遇到角色写占位符[Name]。
        输出 JSON: {{"segments": [...]}}
        """
        
        input_json = json.dumps([{"id":i,"text":s.get('text','')} for i,s in enumerate(final_segments)], ensure_ascii=False)
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model":model,"messages":[{"role":"system","content":sys_prompt},{"role":"user","content":input_json}],"response_format":{"type":"json_object"}}, headers=get_headers(key), timeout=90)
        
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
        # 兜底
        fallback = []
        for seg in final_segments:
            dur = seg.get('duration')
            if dur is None: dur = max(2.0, len(seg.get('text','')) * 0.22)
            fallback.append({"duration": dur, "script": seg.get('text'), "type": "SCENE", "final_prompt": f"Chinese suspense shot, {style}"})
        return pd.DataFrame(fallback)

# 【修复核心】防止 KeyError
def inject_character_prompts(shot_df, char_df):
    # 检查 DataFrame 是否为空，或者是否缺少列
    if shot_df is None or shot_df.empty or 'final_prompt' not in shot_df.columns:
        # 如果有问题，返回一个安全的空表
        return pd.DataFrame(columns=['duration', 'script', 'type', 'final_prompt'])
    
    char_dict = {f"[{row['name']}]": row['prompt'] for _, row in char_df.iterrows()}
    
    def replace(p):
        for ph in re.findall(r'\[.*?\]', str(p)):
            if ph in char_dict: p = p.replace(ph, f"({char_dict[ph]}, Chinese face:1.4)")
        if "Chinese" not in str(p): p = f"(Chinese environment:1.3), {p}"
        return p
        
    shot_df['final_prompt'] = shot_df['final_prompt'].apply(replace)
    return shot_df

def generate_image(prompt, size, key):
    try:
        width, height = 1280, 720 if "16:9" in size else 720, 1280
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model":"black-forest-labs/FLUX.1-schnell","prompt":prompt,"image_size":f"{width}x{height}","batch_size":1,"num_inference_steps":4,"guidance_scale":3.5}, headers=get_headers(key), timeout=50)
        return res.json()['images'][0]['url'] if res.status_code == 200 else "Error"
    except: return "Error"

# 【修复核心】ZIP 结构优化：外层包裹一个文件夹
def create_draft_zip(shot_df, imgs, audio_bytes, audio_name):
    buf = io.BytesIO()
    generator = JianyingDraftGenerator()
    total_duration_us = int(shot_df['duration'].sum() * 1000000)
    generator.add_audio_track(audio_name, total_duration_us)
    generator.add_media_track(shot_df, total_duration_us)
    
    draft_content = generator.generate_json()
    draft_meta = {"id": draft_content["id"], "name": "Mystery_Project", "last_modified": int(time.time()*1000)}
    
    # 简单的占位文件，让剪映觉得这是个正经草稿
    virtual_store = {"virtual_objects": []}

    # 定义根目录名
    root_dir = "Mystery_Project_Draft"

    with zipfile.ZipFile(buf, "w") as zf:
        # 把文件都写在 Mystery_Project_Draft/ 目录下
        zf.writestr(f"{root_dir}/draft_content.json", json.dumps(draft_content, indent=4))
        zf.writestr(f"{root_dir}/draft_meta_info.json", json.dumps(draft_meta, indent=4))
        zf.writestr(f"{root_dir}/draft_virtual_store.json", json.dumps(virtual_store, indent=4))
        
        zf.writestr(f"{root_dir}/media/{audio_name}", audio_bytes)
        for i, u in imgs.items():
            try: zf.writestr(f"{root_dir}/media/{i+1:03d}.jpg", requests.get(u).content)
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
    st.markdown("### 🕵️ 博主"); fixed_host = st.text_area("Prompt", "(A 30-year-old Chinese man, Asian face, black hair, green cap, leather jacket:1.4), looking at camera", height=80)
    st.markdown("### 🧠 设置"); model = st.selectbox("大脑", ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"])
    aspect = st.selectbox("画幅", ["16:9 (横屏)", "9:16 (竖屏)"])
    style = st.text_area("风格", "Film noir, suspense thriller, Chinese background.", height=60)
    st.info("🎨 绘图: FLUX.1-schnell")

st.title("🛠️ MysteryNarrator V26 (工程修复版)")
st.caption("修复 KeyError | 优化草稿结构 | 国风修正")

c1, c2 = st.columns(2)
with c1: script_input = st.text_area("1. 粘贴文案 (如果录音听写失败，将使用此文案)", height=150)
with c2: audio = st.file_uploader("2. 上传录音", type=['mp3','wav','m4a'])

if st.button("🔍 3. 智能分析"):
    if not api_key: st.error("请填 Key")
    # 放宽限制：只要有其中一样就行，优先录音
    elif not script_input and not audio: st.error("文案或录音至少要有一个")
    else:
        # 处理音频
        if audio:
            st.session_state.audio_data = {"name": audio.name, "bytes": audio.getvalue()}
            with st.spinner("听写中..."):
                asr = transcribe_audio(audio, api_key)
                if asr and 'segments' in asr:
                    st.session_state.segments = asr['segments']
                    st.success("✅ 录音对齐成功")
                else:
                    st.session_state.segments = []
                    st.warning("⚠️ 听写失败，将使用文案估算")
        else:
            # 没传音频，造一个假的音频数据防止报错
            st.session_state.audio_data = {"name": "silent.mp3", "bytes": b""}
            st.session_state.segments = []

        # 处理角色
        if script_input:
            df = extract_characters_silicon(script_input, model, api_key)
            host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
            st.session_state.char_df = pd.concat([host, df], ignore_index=True)
        else:
            # 没文案就只留博主
            st.session_state.char_df = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
            st.warning("⚠️ 没提供文案，只能生成博主画面")

if st.session_state.char_df is not None:
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed", use_container_width=True)
    if st.button("🎬 4. 生成分镜"):
        with st.spinner("导演设计中..."):
            c_list = st.session_state.char_df['name'].tolist()
            # 确保 script_input 不为 None
            safe_script = script_input if script_input else ""
            df = analyze_segments_robust(st.session_state.segments, safe_script, c_list, style, aspect, model, api_key)
            
            # 【关键】这里不会再报 KeyError 了
            st.session_state.shot_df = inject_character_prompts(df, st.session_state.char_df)
            
            if st.session_state.shot_df.empty:
                st.error("❌ 生成的分镜表为空！请检查是否输入了有效的文案。")
            else:
                st.success("OK")

if st.session_state.shot_df is not None and not st.session_state.shot_df.empty:
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
            st.download_button("⬇️ 下载草稿包", zip_buf.getvalue(), "Jianying_Mystery_Draft.zip", "application/zip", type="primary")
        else: st.warning("先绘图")
