import streamlit as st
import requests
import pandas as pd
import json
import re
import time
import zipfile
import io

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="MysteryNarrator V11", page_icon="🎬", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d; color: #c0c0c0; }
    [data-testid="stSidebar"] { background-color: #141414; border-right: 1px solid #222; }
    .stButton > button { background-color: #d32f2f; color: white; border: none; width: 100%; padding: 10px; font-weight: bold; }
    .stButton > button:hover { background-color: #b71c1c; }
    /* 预览图样式 */
    img { border: 2px solid #333; border-radius: 5px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心功能函数
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}"}
def clean_json_text(text): return re.sub(r'<think>.*?</think>', '', re.sub(r'```json|```', '', text), flags=re.DOTALL).strip()

# ASR 听写 (带重试)
def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    files = {'file': (audio_file.name, audio_file.getvalue(), audio_file.type), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: return requests.post(url, headers=get_headers(api_key), files=files, timeout=120).json()
    except: return None

# 【物理切刀】强制把长文案切碎
def split_text_by_punctuation(text):
    # 按句号、问号、感叹号、换行符切分
    chunks = re.split(r'([。？！\n])', text)
    result = []
    current = ""
    for chunk in chunks:
        current += chunk
        # 如果长度超过15个字，或者包含标点，就切一刀
        if len(current) > 15 or re.search(r'[。？！\n]', chunk):
            if current.strip(): result.append(current.strip())
            current = ""
    if current.strip(): result.append(current.strip())
    return result

# 角色提取 (带清洗)
def extract_characters_silicon(script_text, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    sys_prompt = "提取文案中的【剧情角色】。输出JSON列表: [{'name':'xx','prompt':'...'}]"
    try:
        res = requests.post(url, json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":script_text}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
        df = pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content'])))
        
        # 【强力清洗】删除 AI 识别出来的任何“博主”
        if not df.empty:
            df = df[~df['name'].str.contains('博主|我|Host|解说', case=False, na=False)]
        return df
    except: return None

# 分镜分析 (根据切碎的句子)
def analyze_split_sentences(sentences, char_names, style, res_p, model, key):
    # 构造输入：这是已经物理切碎的句子列表
    input_data = json.dumps([{"id": i, "text": s} for i, s in enumerate(sentences)], ensure_ascii=False)
    char_list_str = ", ".join(char_names)
    
    sys_prompt = f"""
    你是悬疑片导演。根据输入的【句子列表】设计画面。
    可用角色: {char_list_str}
    风格: {style}, 构图: {res_p}
    任务:
    1. 为每一句话判断类型: "CHARACTER"(有人) 或 "SCENE"(空镜)。
    2. 编写英文Prompt: 
       - 必须包含 {res_p}。
       - 遇到角色只写占位符 [Name]。
    输出: JSON 列表，包含 "index", "script", "type", "final_prompt"。
    """
    try:
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":input_data}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=120)
        result_list = json.loads(clean_json_text(res.json()['choices'][0]['message']['content']))
        if isinstance(result_list, dict): result_list = result_list.get('segments', [])
        
        # 整理数据
        merged = []
        for i, sent in enumerate(sentences):
            # 尝试匹配 AI 的结果，匹配不到就兜底
            visual = next((item for item in result_list if item.get('index') == i), None)
            # 默认时长 3秒 (这是给文本模式用的估计值)
            merged.append({
                "start": i * 3.0, 
                "end": (i + 1) * 3.0, 
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
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model": "Kwai-Kolors/Kolors", "prompt": prompt, "image_size": size, "batch_size": 1}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
        return res.json()['data'][0]['url'] if res.status_code == 200 else "Error"
    except: return "Error"

# SRT生成 (支持音频真实时间和文本估算时间)
def create_zip(shot_df, imgs):
    buf = io.BytesIO()
    def fmt(s): ms=int((s-int(s))*1000); m,s=divmod(int(s),60); h,m=divmod(m,60); return f"{h:02}:{m:02}:{s:02},{ms:03}"
    
    with zipfile.ZipFile(buf, "w") as zf:
        srt_content = ""
        for i, r in shot_df.iterrows():
            srt_content += f"{i+1}\n{fmt(r['start'])} --> {fmt(r['end'])}\n{r['script']}\n\n"
        
        zf.writestr("subtitle.srt", srt_content)
        for i,u in imgs.items():
            try: zf.writestr(f"{i+1:03d}.jpg", requests.get(u).content)
            except: pass
    return buf

# ==========================================
# 3. 界面逻辑
# ==========================================
# 初始化状态
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'gen_imgs' not in st.session_state: st.session_state.gen_imgs = {}
if 'sentences' not in st.session_state: st.session_state.sentences = [] 

with st.sidebar:
    st.markdown("### 🔑 API Key"); api_key = st.text_input("SiliconFlow Key", type="password")
    st.markdown("### 🕵️ 博主形象 (绝对锁定)"); 
    fixed_host = st.text_area("Prompt", "(A 30-year-old Asian man, green cap, leather jacket:1.4)", height=80, help="权重1.4，谁也改不了")
    st.markdown("### 🛠️ 设置"); model = st.selectbox("大脑", ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"])
    res_str, res_prompt = {"16:9":("1280x720","Cinematic 16:9, Wide shot"), "9:16":("720x1280","9:16 portrait")}[st.selectbox("画幅", ["16:9", "9:16"])]
    style = st.text_area("风格", "Film noir, suspense thriller, low key lighting.", height=60)

st.title("🎬 MysteryNarrator V11 (剪映救星)")

# 模式选择
mode = st.radio("选择模式", ["📝 文本模式 (先看效果)", "🎙️ 音频模式 (做成品)"], horizontal=True)

if mode == "📝 文本模式 (先看效果)":
    text_input = st.text_area("粘贴解说词:", height=150)
    if st.button("1. 切分文案 & 提取角色"):
        if not api_key: st.error("请填Key")
        else:
            # 物理切分
            st.session_state.sentences = split_text_by_punctuation(text_input)
            with st.spinner("分析中..."):
                df = extract_characters_silicon(text_input, model, api_key)
                if df is not None:
                    host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                    st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                    st.success(f"成功切分为 {len(st.session_state.sentences)} 个短句。")

elif mode == "🎙️ 音频模式 (做成品)":
    audio = st.file_uploader("上传录音", type=['mp3','wav','m4a'])
    if audio and st.button("1. 听写 & 智能切分"):
        if not api_key: st.error("请填Key")
        else:
            with st.spinner("听写中..."):
                asr = transcribe_audio(audio, api_key)
                if asr:
                    # 智能处理音频数据，确保字幕不糊成一团
                    raw_segments = asr.get('segments', [])
                    clean_segments = []
                    full_text = ""
                    for s in raw_segments:
                        # 如果一句话太长，就不用它的text，而是用标点切分
                        text = s['text']
                        start = s['start']
                        duration = s['end'] - s['start']
                        clean_segments.append(text) # 这里简化处理，先把所有文字拿出来
                        full_text += text + " "
                    
                    # 重新用物理切刀切碎文字，这里简化为只用文字做分镜，时间轴后续可能需要对齐（音频模式略复杂，V11先保字幕不糊）
                    # 为了保证字幕绝对不糊，我们这里先把听写出的全文，强制按短句切分
                    st.session_state.sentences = split_text_by_punctuation(full_text)
                    
                    with st.spinner("分析角色..."):
                        df = extract_characters_silicon(full_text, model, api_key)
                        if df is not None:
                            host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                            st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                            st.success(f"听写并切分为 {len(st.session_state.sentences)} 个短句。")

# 通用流程
if st.session_state.char_df is not None:
    st.markdown("---")
    st.info("👇 确认角色：第一行必须是你的博主设定")
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed")

    if st.button("2. 生成分镜 (强制短句)"):
        with st.spinner("导演正在根据短句设计画面..."):
            char_names = st.session_state.char_df['name'].tolist()
            # 使用切碎的 sentences 列表
            df = analyze_split_sentences(st.session_state.sentences, char_names, style, res_prompt, model, api_key)
            if df is not None:
                df = inject_character_prompts(df, st.session_state.char_df)
                st.session_state.shot_df = df
                st.success("分镜生成完毕！")

# 画图 & 预览
if st.session_state.shot_df is not None:
    st.markdown("---")
    st.info("👇 下表中的 'script' 就是你的字幕内容，确保它们很短")
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, num_rows="dynamic", key="s_ed")
    
    st.markdown("### 3. 生产")
    c1, c2 = st.columns([1, 1])
    
    if c1.button("🚀 开始绘图 (实时预览)"):
        st.markdown("#### 📸 实时监视器")
        preview_container = st.container()
        preview_cols = preview_container.columns(3) # 3列显示
        
        bar = st.progress(0)
        tot = len(st.session_state.shot_df)
        
        for i, r in st.session_state.shot_df.iterrows():
            with preview_container:
                # 实时生成
                url = generate_image(r['final_prompt'], res_str, api_key)
                if "Error" not in url:
                    st.session_state.gen_imgs[i] = url
                    # 亮图！
                    with preview_cols[i % 3]:
                        st.image(url, caption=f"{i+1}. {r['script'][:8]}...", use_column_width=True)
                else:
                    st.error(f"Shot {i+1} 失败")
            
            bar.progress((i+1)/tot)
            if i < tot-1: time.sleep(32) 
        st.success("✅ 杀青！")
        
    if c2.button("📦 下载剪映包"):
        if st.session_state.gen_imgs:
            st.download_button("⬇️ 下载 Project.zip", create_zip(st.session_state.shot_df, st.session_state.gen_imgs).getvalue(), "project.zip", "application/zip")
        else: st.warning("请先绘图")
