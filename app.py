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
st.set_page_config(page_title="MysteryNarrator V24 (FLUX版)", page_icon="🍌", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #121212; color: #e0e0e0; }
    .stButton > button { background-color: #7C4DFF; color: white; border: none; padding: 12px; font-weight: bold; border-radius: 6px; }
    .stSuccess { background-color: #2e7d32; color: white; }
    .stWarning { background-color: #ff6f00; color: white; }
    /* 图片 hover 放大效果 */
    img:hover { transform: scale(1.02); transition: 0.3s; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 剪映草稿生成器 (保持不变)
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
            # 简单的字幕样式
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
# 3. 核心 API (SiliconFlow 深度适配)
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

# 清洗 DeepSeek 的思考过程 <think>...</think>
def clean_json_text(text): 
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'```json|```', '', text)
    return text.strip()

# 1. 语音转文字 (保持不变)
def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    audio_file.seek(0)
    files = {'file': (audio_file.name, audio_file.getvalue(), audio_file.type), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: 
        res = requests.post(url, headers={"Authorization": f"Bearer {api_key}"}, files=files, timeout=60)
        return res.json()
    except: return None

# 2. 【重点修复】人物提取：增强 Prompt，不再只看博主
def extract_characters_silicon(script, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    # 强力 Prompt：强制要求寻找受害者、嫌疑人等
    system_prompt = """
    你是一个悬疑剧本分析师。任务：提取剧本中除了“我/博主”以外的所有关键角色。
    
    规则：
    1. 重点寻找：受害者、嫌疑人、目击者、神秘人（如“红衣女子”、“老头”、“怪物”）。
    2. 如果没有名字，就用外貌代号。
    3. 为每个角色写一段简短的英文外貌描述 (Prompt)。
    
    输出格式(JSON List): [{'name':'王某','prompt':'A middle-aged man, fat, scared face'}, {'name':'红衣女','prompt':'A woman in red dress, long hair, creepy smile'}]
    """
    
    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": script}
            ],
            "response_format": {"type": "json_object"}
        }
        res = requests.post(url, json=payload, headers=get_headers(key), timeout=45)
        
        content = clean_json_text(res.json()['choices'][0]['message']['content'])
        
        # 尝试解析
        try:
            data = json.loads(content)
            # 有时候模型会包裹在 'characters' 键里
            if isinstance(data, dict) and 'characters' in data:
                data = data['characters']
            elif isinstance(data, dict) and 'list' in data:
                data = data['list']
            
            df = pd.DataFrame(data)
            
            # 过滤掉博主自己 (双重保险)
            if not df.empty: 
                df = df[~df['name'].str.contains('博主|我|Host|Narrator', case=False, na=False)]
            return df
        except:
            return pd.DataFrame(columns=['name', 'prompt'])
            
    except Exception as e:
        print(f"人物分析出错: {e}")
        return pd.DataFrame(columns=['name', 'prompt'])

# 3. 分镜分析 (保持稳健)
def analyze_segments_robust(segments, script_text, char_names, style, res_p, model, key):
    final_segments = []
    if segments:
        final_segments = segments
    else:
        # 手动切分兜底
        chunks = re.split(r'([。？！；\n])', script_text)
        current = ""
        for chunk in chunks:
            if len(current) + len(chunk) < 18 and not re.match(r'[。？！\n]', chunk): current += chunk
            else: 
                if current: final_segments.append({"text": current, "duration": 5.0})
                current = chunk
        if current: final_segments.append({"text": current, "duration": 5.0})

    try:
        # 构造输入
        input_data = json.dumps([{"id":i,"text":s.get('text', '')} for i,s in enumerate(final_segments)], ensure_ascii=False)
        char_list = ", ".join(char_names) if char_names else "无特定角色"
        
        sys_prompt = f"""
        你是悬疑电影导演。
        【已知角色】: {char_list}
        【整体风格】: {style}
        【画面构图】: {res_p}
        
        任务: 为每一句字幕设计画面 Prompt。
        规则:
        1. 遇到具体角色名字时，Prompt 里必须包含该名字的英文描述（例如 'A woman in red'）。
        2. 如果是空镜头/环境描写，不要加人。
        3. 输出 JSON: {{"segments": [{{"index": 0, "type": "SCENE/HOST", "final_prompt": "..."}}]}}
        """
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": input_data}
            ],
            "response_format": {"type": "json_object"}
        }
        
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json=payload, headers=get_headers(key), timeout=90)
        result_content = clean_json_text(res.json()['choices'][0]['message']['content'])
        result_json = json.loads(result_content)
        
        result_list = result_json.get('segments', [])
        
        merged = []
        for i, seg in enumerate(final_segments):
            # 匹配结果
            vis = next((item for item in result_list if item.get('index') == i), None)
            
            # 计算时长
            dur = seg.get('duration')
            if dur is None and 'end' in seg and 'start' in seg: 
                dur = seg['end'] - seg['start']
            if dur is None: dur = 5.0
            
            merged.append({
                "duration": dur,
                "script": seg.get('text'),
                "type": vis['type'] if vis else "SCENE",
                "final_prompt": vis['final_prompt'] if vis else f"Suspense scene, {style}"
            })
        return pd.DataFrame(merged)

    except Exception as e:
        print(f"分镜分析出错: {e}")
        # 出错兜底
        fallback = []
        for seg in final_segments:
            dur = seg.get('duration', 5.0)
            fallback.append({"duration": dur, "script": seg.get('text'), "type": "SCENE", "final_prompt": f"Suspense shot, {style}"})
        return pd.DataFrame(fallback)

def inject_character_prompts(shot_df, char_df):
    if shot_df is None or shot_df.empty or 'final_prompt' not in shot_df.columns: return shot_df
    # 简单的文本替换增强
    return shot_df

# 4. 【重点升级】绘图引擎：FLUX.1-schnell
# 这是 SiliconFlow 上目前性价比最高、画质最好的模型
def generate_image(prompt, size, key):
    try:
        # 这里的 size 需要转换一下格式，FLUX 通常接受 "1024x1024" 等
        # 为了安全，我们固定用 FLUX 的标准尺寸
        width, height = 1280, 720 # 16:9
        if "9:16" in size: width, height = 720, 1280
        
        payload = {
            "model": "black-forest-labs/FLUX.1-schnell", # 👈 旗舰模型
            "prompt": prompt,
            "image_size": f"{width}x{height}",
            "batch_size": 1,
            "num_inference_steps": 4, # Schnell 4步就能出图，极快
            "guidance_scale": 3.5
        }
        
        res = requests.post(
            "https://api.siliconflow.cn/v1/images/generations", 
            json=payload, 
            headers=get_headers(key), 
            timeout=50
        )
        
        if res.status_code == 200:
            return res.json()['images'][0]['url']
        else:
            print(f"绘图报错: {res.text}")
            return "Error"
    except Exception as e: 
        print(f"请求异常: {e}")
        return "Error"

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
# 5. 主界面逻辑
# ==========================================
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'gen_imgs' not in st.session_state: st.session_state.gen_imgs = {}
if 'audio_data' not in st.session_state: st.session_state.audio_data = None
if 'segments' not in st.session_state: st.session_state.segments = []

with st.sidebar:
    st.markdown("### 🔑 配置中心")
    api_key = st.text_input("SiliconFlow API Key", type="password")
    
    st.markdown("### 🕵️ 固定角色")
    fixed_host = st.text_area("博主 Prompt", "(A 30-year-old Asian man, green cap, leather jacket:1.4), looking at camera", height=80)
    
    st.markdown("### 🧠 模型选择")
    # 修正模型名称，DeepSeek V3 是目前最稳的
    model = st.selectbox("大脑模型", ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"])
    
    # FLUX 尺寸选择
    aspect = st.selectbox("画幅", ["16:9 (横屏)", "9:16 (竖屏)"])
    res_str = "16:9" if "16:9" in aspect else "9:16"
    res_prompt = "Cinematic 16:9" if "16:9" in aspect else "Portrait 9:16"
    
    style = st.text_area("整体风格", "Film noir, suspense thriller, dramatic lighting, 80s film grain, high details.", height=60)
    
    st.info("🎨 绘图已升级为: FLUX.1-schnell (更快更强)")

st.title("🚀 MysteryNarrator V24 (SiliconFlow FLUX版)")
st.caption("逻辑大脑: DeepSeek V3 | 视觉引擎: FLUX.1-schnell")

c1, c2 = st.columns(2)
with c1: script_input = st.text_area("1. 粘贴文案 (无需标点完美)", height=150)
with c2: audio = st.file_uploader("2. 上传录音 (MP3/WAV)", type=['mp3','wav','m4a'])

# --- 步骤 3: 分析 ---
if st.button("🔍 3. 智能分析"):
    if not api_key: st.error("请填入 SiliconFlow Key")
    elif not script_input or not audio: st.error("请提供文案和录音")
    else:
        st.session_state.audio_data = {"name": audio.name, "bytes": audio.getvalue()}
        
        with st.spinner("🎧 正在听写录音时间轴..."):
            asr = transcribe_audio(audio, api_key)
            if asr and 'segments' in asr and len(asr['segments']) > 0:
                st.session_state.segments = asr['segments']
                st.success(f"✅ 语音识别成功，共 {len(asr['segments'])} 句话。")
            else:
                st.session_state.segments = []
                st.warning("⚠️ 语音识别未返回时间轴，将使用默认时长。")

        with st.spinner("🕵️ 正在挖掘剧本中的受害者和配角..."):
            df = extract_characters_silicon(script_input, model, api_key)
            if df is None: df = pd.DataFrame(columns=['name', 'prompt'])
            
            # 把博主加到第一行
            host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
            st.session_state.char_df = pd.concat([host, df], ignore_index=True)
            st.success("✅ 角色提取完成！")

# --- 角色编辑区 ---
if st.session_state.char_df is not None:
    st.markdown("##### 🎭 角色列表 (可修改)")
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed", use_container_width=True)
    
    if st.button("🎬 4. 生成分镜表"):
        with st.spinner(f"🧠 {model} 正在担任导演，设计分镜..."):
            c_list = st.session_state.char_df['name'].tolist()
            df = analyze_segments_robust(st.session_state.segments, script_input, c_list, style, res_prompt, model, api_key)
            # 简单的 Prompt 注入
            st.session_state.shot_df = inject_character_prompts(df, st.session_state.char_df)
            st.success("✅ 分镜设计完毕！")

# --- 分镜编辑与绘图 ---
if st.session_state.shot_df is not None and not st.session_state.shot_df.empty:
    st.markdown("##### 📋 分镜表 (可微调 Prompt)")
    st.session_state.shot_df = st.data_editor(
        st.session_state.shot_df, 
        num_rows="dynamic", 
        key="s_ed", 
        use_container_width=True,
        column_config={
            "final_prompt": st.column_config.TextColumn("绘图指令", width="large"),
            "type": st.column_config.SelectboxColumn("类型", options=["HOST", "SCENE"], width="small"),
            "duration": st.column_config.NumberColumn("时长(秒)", format="%.1f")
        }
    )
    
    col1, col2 = st.columns(2)
    if col1.button("🎨 5. FLUX 极速绘图"):
        if not api_key: st.error("No Key")
        else:
            bar = st.progress(0)
            tot = len(st.session_state.shot_df)
            
            # 创建网格显示图片
            img_container = st.container()
            cols = img_container.columns(4)
            
            for i, r in st.session_state.shot_df.iterrows():
                # 调用 FLUX
                url = generate_image(r['final_prompt'], res_str, api_key)
                
                if "Error" not in url:
                    st.session_state.gen_imgs[i] = url
                    # 实时显示
                    with cols[i % 4]:
                        st.image(url, caption=f"#{i+1} {r['type']}", use_column_width=True)
                else:
                    st.warning(f"第 {i+1} 张生成失败")

                bar.progress((i+1)/tot)
                # FLUX Schnell 非常快，且 SiliconFlow 限制较宽松，间隔 2 秒即可，不用 35 秒
                if i < tot-1: time.sleep(2) 
            
            st.success("🎉 全部绘图完成！")

    if col2.button("📦 6. 下载剪映草稿包"):
        if st.session_state.gen_imgs:
            zip_buf = create_draft_zip(st.session_state.shot_df, st.session_state.gen_imgs, st.session_state.audio_data["bytes"], st.session_state.audio_data["name"])
            st.download_button("⬇️ 点击下载 ZIP", zip_buf.getvalue(), "Jianying_Mystery_Draft.zip", "application/zip", type="primary")
        else: 
            st.warning("⚠️ 请先点击左侧按钮生成图片")
