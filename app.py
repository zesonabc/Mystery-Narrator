import streamlit as st
import requests
import pandas as pd
import json
import re
import time
import os
import random
# 引入 moviepy 的高级特效模块
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, ColorClip
import moviepy.video.fx.all as vfx

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="MysteryNarrator V13 (动态运镜版)", page_icon="🎥", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d; color: #c0c0c0; }
    .stButton > button { background-color: #d32f2f; color: white; width: 100%; padding: 10px; font-weight: bold; }
    .stButton > button:hover { background-color: #b71c1c; }
    .stSuccess { background-color: #1b5e20 !important; }
    img { border: 1px solid #333; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

if not os.path.exists("temp"): os.makedirs("temp")

# ==========================================
# 2. 核心功能
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}"}
def clean_json_text(text): return re.sub(r'<think>.*?</think>', '', re.sub(r'```json|```', '', text), flags=re.DOTALL).strip()

# ASR
def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    temp_path = f"temp/{audio_file.name}"
    with open(temp_path, "wb") as f: f.write(audio_file.getbuffer())
    files = {'file': open(temp_path, "rb"), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: 
        res = requests.post(url, headers=get_headers(api_key), files=files, timeout=120).json()
        return res, temp_path
    except: return None, None

# 字幕强制切分
def split_long_segments(segments, max_len=18):
    new_segments = []
    for seg in segments:
        text = seg['text']; start = seg['start']; end = seg['end']; duration = end - start
        if len(text) > max_len:
            parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]
            part_dur = duration / len(parts)
            for i, part in enumerate(parts):
                new_segments.append({"text": part, "start": start + (i*part_dur), "end": start + ((i+1)*part_dur)})
        else: new_segments.append(seg)
    return new_segments

# 角色提取
def extract_characters_silicon(script, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    try:
        res = requests.post(url, json={"model":model, "messages":[{"role":"system","content":"提取【剧情角色】输出JSON列表:[{'name':'xx','prompt':'...'}]"},{"role":"user","content":script}], "response_format":{"type":"json_object"}}, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, timeout=60)
        df = pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])))
        if not df.empty: df = df[~df['name'].str.contains('博主|我|Host', case=False, na=False)]
        return df
    except: return None

# 分镜分析
def analyze_segments(segments, char_names, style, res_p, model, key):
    input_data = json.dumps([{"id":i,"text":s['text']} for i,s in enumerate(segments)], ensure_ascii=False)
    char_list = ", ".join(char_names)
    sys_prompt = f"""
    悬疑导演模式。角色:{char_list}。风格:{style}。构图:{res_p}。
    任务: 为每一句字幕设计画面。类型: CHARACTER/SCENE。Prompt: 遇角色写占位符[Name]。
    输出JSON列表 "index", "type", "final_prompt"
    """
    try:
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model":model,"messages":[{"role":"system","content":sys_prompt},{"role":"user","content":input_data}],"response_format":{"type":"json_object"}}, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, timeout=120)
        result_list = json.loads(clean_json_text(res.json()['choices'][0]['message']['content']))
        if isinstance(result_list, dict): result_list = result_list.get('segments', [])
        merged = []
        for i, seg in enumerate(segments):
            vis = next((item for item in result_list if item.get('index') == i), None)
            merged.append({"start":seg['start'],"end":seg['end'],"script":seg['text'],"type":vis['type'] if vis else "SCENE","final_prompt":vis['final_prompt'] if vis else f"{style} scene"})
        return pd.DataFrame(merged)
    except: return None

# 角色注入
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
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model":"Kwai-Kolors/Kolors","prompt":prompt,"image_size":size,"batch_size":1}, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, timeout=60)
        return res.json()['data'][0]['url'] if res.status_code == 200 else "Error"
    except: return "Error"

# 【核心升级】添加动态运镜效果 (Ken Burns Effect)
def add_dynamic_motion(image_clip, duration, resolution_type):
    w, h = image_clip.size
    
    # 1. 定义运镜类型（随机选择）
    # zoom_in: 推近, zoom_out: 拉远, pan: 平移
    move_type = random.choice(['zoom_in', 'zoom_out', 'pan', 'pan']) # 稍微增加平移的概率
    
    # 2. 基础放大 (为了有空间移动，先把图放大 10%)
    zoom_ratio = 1.1
    enlarged_clip = image_clip.resize(zoom_ratio)
    ew, eh = enlarged_clip.size
    
    # 计算最大可移动范围
    max_x = ew - w
    max_y = eh - h

    # 3. 根据类型定义起始和结束的裁剪框 (Crop Box)
    if move_type == 'zoom_in':
        # 从全图 -> 中心局部
        x1_start, y1_start = 0, 0
        x1_end, y1_end = max_x / 2, max_y / 2
        
    elif move_type == 'zoom_out':
        # 从中心局部 -> 全图
        x1_start, y1_start = max_x / 2, max_y / 2
        x1_end, y1_end = 0, 0
        
    else: # 'pan' 平移
        # 随机选择起点和终点
        x1_start = random.randint(0, int(max_x))
        y1_start = random.randint(0, int(max_y))
        
        # 确保移动距离足够大，避免画面不动
        if resolution_type == "16:9": # 横屏倾向于水平移
             x1_end = random.randint(0, int(max_x))
             y1_end = y1_start + random.randint(-int(max_y*0.2), int(max_y*0.2)) # Y轴微动
        else: # 竖屏倾向于垂直移
             x1_end = x1_start + random.randint(-int(max_x*0.2), int(max_x*0.2)) # X轴微动
             y1_end = random.randint(0, int(max_y))

    # 边界检查
    x1_end = max(0, min(x1_end, max_x))
    y1_end = max(0, min(y1_end, max_y))

    # 4. 应用动态裁剪 (关键函数)
    # 使用 lambda 函数根据时间 t 插值计算当前的裁剪坐标
    moving_clip = enlarged_clip.crop(
        x1=lambda t: x1_start + (x1_end - x1_start) * (t / duration),
        y1=lambda t: y1_start + (y1_end - y1_start) * (t / duration),
        width=w, height=h
    ).set_duration(duration)

    return moving_clip

# 【升级】渲染视频 (加入运镜)
def render_video_with_motion(shot_df, image_paths, audio_path, res_type):
    clips = []
    # 获取目标分辨率
    target_w, target_h = (1280, 720) if res_type == "16:9" else (720, 1280)
    
    for i, row in shot_df.iterrows():
        duration = row['end'] - row['start']
        # 最小片段时长，防止报错
        if duration < 0.5: duration = 0.5
            
        img_path = image_paths.get(i)
        
        if img_path and os.path.exists(img_path):
            # 读取图片并强制设为目标分辨率，防止尺寸不一报错
            base_clip = ImageClip(img_path).resize(newsize=(target_w, target_h))
            # 【关键】应用动态运镜
            motion_clip = add_dynamic_motion(base_clip, duration, res_type)
            clips.append(motion_clip)
        else:
            # 如果缺图，用黑色片段代替，保证音频对齐
            black_clip = ColorClip(size=(target_w, target_h), color=(0,0,0)).set_duration(duration)
            clips.append(black_clip)

    if not clips: return None
    # 拼接
    final_video = concatenate_videoclips(clips, method="compose")
    # 加音频
    audio = AudioFileClip(audio_path)
    final_video = final_video.set_audio(audio)
    final_video.duration = audio.duration # 强制以音频长度为准
    
    output_filename = "temp/final_motion_output.mp4"
    # 渲染 (fps=24 看起来更顺滑)
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac", preset="fast")
    return output_filename

# SRT
def create_srt(shot_df):
    def fmt(s): ms=int((s-int(s))*1000); m,s=divmod(int(s),60); h,m=divmod(m,60); return f"{h:02}:{m:02}:{s:02},{ms:03}"
    return "".join([f"{i+1}\n{fmt(r['start'])} --> {fmt(r['end'])}\n{r['script']}\n\n" for i,r in shot_df.iterrows()])

# ==========================================
# 3. 界面逻辑
# ==========================================
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'image_paths' not in st.session_state: st.session_state.image_paths = {}
if 'segments' not in st.session_state: st.session_state.segments = None 
if 'audio_path' not in st.session_state: st.session_state.audio_path = None

with st.sidebar:
    st.markdown("### 🔑 API Key"); api_key = st.text_input("SiliconFlow Key", type="password")
    st.markdown("### 🕵️ 博主形象"); fixed_host = st.text_area("Prompt", "(A 30-year-old Asian man, green cap, leather jacket:1.4)", height=80)
    st.markdown("### 🛠️ 设置"); model = st.selectbox("大脑", ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"])
    res_opt = st.selectbox("画幅", ["16:9", "9:16"]); 
    res_type = "16:9" if res_opt == "16:9" else "9:16"
    res_str, res_prompt = {"16:9":("1280x720","Cinematic 16:9"), "9:16":("720x1280","9:16 portrait")}[res_opt]
    style = st.text_area("风格", "Film noir, suspense thriller, low key lighting.", height=60)

st.title("🎥 MysteryNarrator V13 (动态运镜版)")
st.caption("上传录音 -> 自动生成带【推拉摇移】效果的成品视频")

audio_file = st.file_uploader("上传录音 (MP3/WAV)", type=['mp3','wav','m4a'])

if audio_file and st.button("1. 听写 & 分析"):
    if not api_key: st.error("请填Key")
    else:
        st.session_state.image_paths = {} # 清空旧图
        with st.spinner("听写并切分字幕..."):
            raw_res, audio_path = transcribe_audio(audio_file, api_key)
            if raw_res:
                st.session_state.audio_path = audio_path
                raw_segments = raw_res.get('segments', [])
                clean_segs = split_long_segments(raw_segments, max_len=18)
                st.session_state.segments = clean_segs
                full_text = "".join([s['text'] for s in clean_segs])
                with st.spinner("提取角色..."):
                    df = extract_characters_silicon(full_text, model, api_key)
                    if df is not None:
                        host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                        st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                        st.success(f"就绪！共 {len(clean_segs)} 个分镜。")

if st.session_state.char_df is not None:
    st.markdown("---")
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed")
    if st.button("2. 生成分镜表"):
        with st.spinner("导演设计中..."):
            char_names = st.session_state.char_df['name'].tolist()
            df = analyze_segments(st.session_state.segments, char_names, style, res_prompt, model, api_key)
            if df is not None:
                df = inject_character_prompts(df, st.session_state.char_df)
                st.session_state.shot_df = df
                st.success("分镜完成")

if st.session_state.shot_df is not None:
    st.markdown("---")
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, num_rows="dynamic", key="s_ed")
    
    if st.button("🚀 3. 渲染动态视频 (MP4)"):
        # 1. 先画图
        st.markdown("#### 🖼️ 阶段一：绘制画面")
        bar = st.progress(0); status = st.empty(); gallery = st.columns(4)
        tot = len(st.session_state.shot_df)
        for i, r in st.session_state.shot_df.iterrows():
            status.text(f"绘制 {i+1}/{tot}: {r['script']}")
            url = generate_image(r['final_prompt'], res_str, api_key)
            if "Error" not in url:
                img_data = requests.get(url).content
                local_path = f"temp/img_{i}.jpg"
                with open(local_path, "wb") as f: f.write(img_data)
                st.session_state.image_paths[i] = local_path
                with gallery[i%4]: st.image(url, use_column_width=True)
            bar.progress((i+1)/tot); 
            if i<tot-1: time.sleep(32)
            
        # 2. 后合成视频
        with st.spinner("🎬 阶段二：正在应用动态运镜并渲染 MP4 (请耐心等待)..."):
            # 传递分辨率类型参数
            video_file = render_video_with_motion(st.session_state.shot_df, st.session_state.image_paths, st.session_state.audio_path, res_type)
            if video_file:
                st.success("🎉 动态视频生成成功！")
                st.video(video_file)
                with open(video_file, "rb") as f: vb = f.read()
                st.download_button("⬇️ 下载最终视频 (MP4)", vb, "final_motion_story.mp4", "video/mp4")
                st.download_button("⬇️ 下载配套字幕 (SRT)", create_srt(st.session_state.shot_df), "subtitle.srt", "text/plain")
            else: st.error("视频渲染失败")
