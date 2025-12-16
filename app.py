import streamlit as st
import requests
import pandas as pd
import json
import re
import time
import zipfile
import io

# ==========================================
# 1. 页面配置 (极简稳定)
# ==========================================
st.set_page_config(page_title="MysteryNarrator V14 (投产版)", page_icon="🏭", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #1e1e1e; color: #e0e0e0; }
    .stButton > button { background-color: #0078d7; color: white; border: none; padding: 12px; font-weight: bold; border-radius: 8px; }
    .stButton > button:hover { background-color: #0063b1; }
    img { border: 2px solid #444; border-radius: 8px; margin-bottom: 8px; }
    .stSuccess { background-color: #107c10 !important; color: white; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心功能函数
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}"}
def clean_json_text(text): return re.sub(r'<think>.*?</think>', '', re.sub(r'```json|```', '', text), flags=re.DOTALL).strip()

# ASR 听写
def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    files = {'file': (audio_file.name, audio_file.getvalue(), audio_file.type), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: return requests.post(url, headers=get_headers(api_key), files=files, timeout=60).json()
    except: return None

# 【物理切刀】强制把长文案切碎 (解决字幕糊屏的核心)
def split_long_text(text, max_len=15):
    # 先按标点切
    chunks = re.split(r'([。？！，；\n])', text)
    result = []
    current = ""
    for chunk in chunks:
        # 如果加上这块还没超长，就拼起来
        if len(current) + len(chunk) < max_len and not re.match(r'[。？！\n]', chunk):
            current += chunk
        else:
            # 否则切一刀
            if current: result.append(current)
            current = chunk
    if current: result.append(current)
    return result

# 角色提取 (带强力清洗)
def extract_characters_silicon(script_text, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    sys_prompt = "提取文案中的【剧情角色】。输出JSON列表: [{'name':'xx','prompt':'...'}]"
    try:
        res = requests.post(url, json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":script_text}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=30)
        df = pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])))
        # 清洗掉 AI 识别错误的博主
        if not df.empty: df = df[~df['name'].str.contains('博主|我|Host|解说', case=False, na=False)]
        return df
    except: return None

# 分镜分析
def analyze_split_sentences(sentences, char_names, style, res_p, model, key):
    # 构造输入
    input_data = json.dumps([{"id": i, "text": s} for i, s in enumerate(sentences)], ensure_ascii=False)
    char_list_str = ", ".join(char_names)
    
    sys_prompt = f"""
    你是悬疑片导演。根据【句子列表】设计画面。
    可用角色: {char_list_str}
    风格: {style}, 构图: {res_p}
    任务:
    1. 判断类型: "CHARACTER"(有人) 或 "SCENE"(空镜)。
    2. Prompt: 遇到角色只写占位符 [Name]。
    输出: JSON 列表 "index", "type", "final_prompt"。
    """
    try:
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":input_data}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
        result_list = json.loads(clean_json_text(res.json()['choices'][0]['message']['content']))
        if isinstance(result_list, dict): result_list = result_list.get('segments', [])
        
        merged = []
        for i, sent in enumerate(sentences):
            visual = next((item for item in result_list if item.get('index') == i), None)
            merged.append({
                # 估算时间：每10个字算2秒，最少2秒
                "duration": max(2.0, len(sent) * 0.2), 
                "script": sent, 
                "type": visual['type'] if visual else "SCENE", 
                "final_prompt": visual['final_prompt'] if visual else f"Suspense scene, {style}"
            })
        return pd.DataFrame(merged)
    except: return None

# 角色注入
def inject_character_prompts(shot_df, char_df):
    if shot_df is None or char_df is None: return shot_df
    char_dict = {f"[{row['name']}]": row['prompt'] for _, row in char_df.iterrows()}
    def replace_placeholder(prompt):
        for ph in re.findall(r'\[.*?\]', prompt):
            if ph in char_dict: prompt = prompt.replace(ph, f"({char_dict[ph]}:1.3)")
        return prompt
    shot_df['final_prompt'] = shot_df['final_prompt'].apply(replace_placeholder)
    return shot_df

# 画图
def generate_image(prompt, size, key):
    try:
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model": "Kwai-Kolors/Kolors", "prompt": prompt, "image_size": size, "batch_size": 1}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=30)
        return res.json()['data'][0]['url'] if res.status_code == 200 else "Error"
    except: return "Error"

# ZIP打包
def create_zip(shot_df, imgs):
    buf = io.BytesIO()
    # 计算SRT时间轴
    current_time = 0.0
    def fmt(s): ms=int((s-int(s))*1000); m,s=divmod(int(s),60); h,m=divmod(m,60); return f"{h:02}:{m:02}:{s:02},{ms:03}"
    
    with zipfile.ZipFile(buf, "w") as zf:
        srt_content = ""
        for i, r in shot_df.iterrows():
            start = current_time
            end = current_time + r['duration']
            srt_content += f"{i+1}\n{fmt(start)} --> {fmt(end)}\n{r['script']}\n\n"
            current_time = end
        
        zf.writestr("subtitle.srt", srt_content)
        for i,u in imgs.items():
            # 【重要】重命名为 001_shot.jpg 保证排序
            try: zf.writestr(f"{i+1:03d}_shot.jpg", requests.get(u).content)
            except: pass
    return buf

# ==========================================
# 3. 界面逻辑
# ==========================================
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'gen_imgs' not in st.session_state: st.session_state.gen_imgs = {}
if 'sentences' not in st.session_state: st.session_state.sentences = [] 

with st.sidebar:
    st.markdown("### 🔑 API Key"); api_key = st.text_input("SiliconFlow Key", type="password")
    st.markdown("### 🕵️ 博主形象 (绝对锁定)"); 
    fixed_host = st.text_area("Prompt", "(A 30-year-old Asian man, green cap, leather jacket:1.4)", height=80)
    st.markdown("### 🛠️ 设置"); model = st.selectbox("大脑", ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"])
    res_str, res_prompt = {"16:9":("1280x720","Cinematic 16:9, Wide shot"), "9:16":("720x1280","9:16 portrait")}[st.selectbox("画幅", ["16:9", "9:16"])]
    style = st.text_area("风格", "Film noir, suspense thriller, low key lighting.", height=60)

st.title("🏭 MysteryNarrator V14 (稳定投产版)")
st.caption("流程：听写 -> 强制切短句 -> 生成素材包 -> 剪映一键合成")

# 模式选择 (默认音频，因为你要做视频)
audio = st.file_uploader("1. 上传录音 (MP3/WAV)", type=['mp3','wav','m4a'])

if audio and st.button("👂 2. 听写 & 智能切片"):
    if not api_key: st.error("请填Key")
    else:
        with st.spinner("正在听写并强制切分..."):
            asr = transcribe_audio(audio, api_key)
            if asr:
                # 1. 拿到全文
                full_text = "".join([s['text'] for s in asr.get('segments', [])])
                # 2. 【核心】强制切碎，每句不超过 15 字
                st.session_state.sentences = split_long_text(full_text, max_len=15)
                
                with st.spinner("分析角色..."):
                    df = extract_characters_silicon(full_text, model, api_key)
                    if df is not None:
                        host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                        st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                        st.success(f"准备就绪！切分为 {len(st.session_state.sentences)} 个短句。")

# 确认角色
if st.session_state.char_df is not None:
    st.markdown("---")
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed")

    if st.button("🎬 3. 生成分镜表"):
        with st.spinner("导演设计中..."):
            char_names = st.session_state.char_df['name'].tolist()
            df = analyze_split_sentences(st.session_state.sentences, char_names, style, res_prompt, model, api_key)
            if df is not None:
                df = inject_character_prompts(df, st.session_state.char_df)
                st.session_state.shot_df = df
                st.success("分镜完成")

# 画图 & 预览
if st.session_state.shot_df is not None:
    st.markdown("---")
    st.info("👇 检查：'script' 列应该都是短句，如果不满意可以手动修改")
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, num_rows="dynamic", key="s_ed")
    
    col1, col2 = st.columns(2)
    if col1.button("🚀 4. 开始绘图"):
        st.markdown("#### 🖼️ 实时预览")
        preview = st.container(); cols = preview.columns(4)
        bar = st.progress(0); tot = len(st.session_state.shot_df)
        
        for i, r in st.session_state.shot_df.iterrows():
            url = generate_image(r['final_prompt'], res_str, api_key)
            if "Error" not in url:
                st.session_state.gen_imgs[i] = url
                with cols[i%4]: st.image(url, caption=f"{i+1}. {r['script']}", use_column_width=True)
            bar.progress((i+1)/tot)
            if i < tot-1: time.sleep(32) # 必须冷却
        st.success("✅ 全部生成完毕！")
        
    if col2.button("📦 5. 下载剪映包"):
        if st.session_state.gen_imgs:
            st.download_button("⬇️ 下载 Project.zip", create_zip(st.session_state.shot_df, st.session_state.gen_imgs).getvalue(), "project.zip", "application/zip")
        else: st.warning("请先绘图")
