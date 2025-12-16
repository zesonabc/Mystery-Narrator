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
st.set_page_config(page_title="MysteryNarrator V9", page_icon="🎬", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d; color: #c0c0c0; }
    [data-testid="stSidebar"] { background-color: #141414; border-right: 1px solid #222; }
    .stButton > button { background-color: #d32f2f; color: white; border: none; width: 100%; font-weight: bold; padding: 10px; }
    .stButton > button:hover { background-color: #b71c1c; }
    .stButton > button:disabled { background-color: #333; color: #666; }
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
    try: return requests.post(url, headers=get_headers(api_key), files=files, timeout=120).json()
    except Exception as e: return None

# 角色提取
def extract_characters_silicon(script_text, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    sys_prompt = "提取文案中的【剧情角色】(不含博主)。输出JSON列表: [{'name':'xx','prompt':'...'}]"
    try:
        res = requests.post(url, json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":script_text}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
        return pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content']))) if res.status_code == 200 else None
    except: return None

# 分镜分析 (支持纯文本模式 + 音频模式)
def analyze_segments_or_text(segments, full_text, char_names, style, res_p, model, key):
    # 构造输入：如果有时间轴用时间轴，没时间轴用纯文本切分
    if segments:
        input_data = json.dumps(segments, ensure_ascii=False)
        task_desc = "为【已分段解说词 JSON】设计画面"
    else:
        # 纯文本模式：让 AI 自己切分
        input_data = full_text
        task_desc = "将文案拆分为3-6秒镜头"

    char_list_str = ", ".join(char_names)
    
    sys_prompt = f"""
    你是悬疑片导演。{task_desc}。
    可用角色名: {char_list_str}
    风格:{style}, 构图:{res_p}
    任务:
    1. 判断类型: "CHARACTER" 或 "SCENE"。
    2. 编写英文Prompt(final_prompt): 
       - **关键规则**: 如果镜头出现角色，**只需写角色名占位符，如 [博主(我)] 或 [Liam]**。
       - 必须包含动作、情绪和风格词。
    输出: 纯 JSON 列表，包含 "index", "script", "type", "final_prompt"。
    """
    try:
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":input_data}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=120)
        if res.status_code == 200:
            result_list = json.loads(clean_json_text(res.json()['choices'][0]['message']['content']))
            if isinstance(result_list, dict): result_list = result_list.get('segments', [])
            
            # 合并逻辑
            merged = []
            if segments: # 音频模式：合并时间轴
                for i, seg in enumerate(segments):
                    visual = next((item for item in result_list if item.get('index') == i), None)
                    merged.append({"start": seg['start'], "end": seg['end'], "script": seg['text'], "type": visual['type'] if visual else "SCENE", "final_prompt": visual['final_prompt'] if visual else f"Suspense scene, {style}"})
            else: # 文本模式：直接用 AI 的切分
                merged = result_list
                # 补充默认时间 (纯文本没时间轴，只能估算)
                for item in merged:
                    if 'start' not in item: item['start'] = 0
                    if 'end' not in item: item['end'] = 3
            return pd.DataFrame(merged)
        return None
    except: return None

# 注入角色
def inject_character_prompts(shot_df, char_df):
    if shot_df is None or char_df is None: return shot_df
    char_dict = {f"[{row['name']}]": row['prompt'] for _, row in char_df.iterrows()}
    def replace_placeholder(prompt):
        for ph in re.findall(r'\[.*?\]', prompt):
            if ph in char_dict: prompt = prompt.replace(ph, f"({char_dict[ph]}:1.2)")
        return prompt
    shot_df['final_prompt'] = shot_df['final_prompt'].apply(replace_placeholder)
    return shot_df

# 画图
def generate_image(prompt, size, key):
    try:
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model": "Kwai-Kolors/Kolors", "prompt": prompt, "image_size": size, "batch_size": 1}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
        return res.json()['data'][0]['url'] if res.status_code == 200 else "Error"
    except: return "Error"

# ZIP
def create_zip(shot_df, imgs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        srt = "".join([f"{i+1}\n00:00:00,000 --> 00:00:03,000\n{r['script']}\n\n" for i,r in shot_df.iterrows()]) # 简易字幕
        zf.writestr("subtitle.srt", srt)
        for i,u in imgs.items():
            try: zf.writestr(f"{i+1:03d}.jpg", requests.get(u).content)
            except: pass
    return buf

# ==========================================
# 3. 界面逻辑
# ==========================================
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'gen_imgs' not in st.session_state: st.session_state.gen_imgs = {}
if 'segments' not in st.session_state: st.session_state.segments = None # 存音频时间轴
if 'full_text' not in st.session_state: st.session_state.full_text = ""

with st.sidebar:
    st.markdown("### 🔑 API Key"); api_key = st.text_input("SiliconFlow Key", type="password")
    st.markdown("### 🕵️ 博主形象"); fixed_host = st.text_area("Prompt", "(A 30-year-old Asian man, green cap, leather jacket:1.3)", height=80)
    st.markdown("### 🛠️ 设置"); model = st.selectbox("大脑", ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"])
    res_str, res_prompt = {"16:9":("1280x720","Cinematic 16:9"), "9:16":("720x1280","9:16 portrait")}[st.selectbox("画幅", ["16:9", "9:16"])]
    style = st.text_area("风格", "Film noir, suspense thriller, low key lighting.", height=60)

st.title("🎬 MysteryNarrator V9 (双模修复版)")

# --- 模式选择 Tab ---
tab1, tab2 = st.tabs(["📝 文本模式 (粘贴文案)", "🎙️ 音频模式 (上传录音)"])

# 模式 A: 文本
with tab1:
    text_input = st.text_area("输入解说词:", height=150, key="txt_in")
    if st.button("🔍 分析文本角色"):
        if not api_key: st.error("请在左侧填入 API Key")
        elif not text_input: st.warning("请先输入文字")
        else:
            st.session_state.segments = None # 清空音频数据
            st.session_state.full_text = text_input
            with st.spinner("正在分析文本角色..."):
                df = extract_characters_silicon(text_input, model, api_key)
                if df is not None:
                    host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                    st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                    st.success("角色提取成功！(文本模式)")

# 模式 B: 音频
with tab2:
    audio = st.file_uploader("上传录音", type=['mp3','wav','m4a'])
    if st.button("👂 听写并分析角色"):
        if not api_key: st.error("请在左侧填入 API Key")
        elif not audio: st.warning("请先上传文件")
        else:
            with st.spinner("正在听写..."):
                asr = transcribe_audio(audio, api_key)
                if asr:
                    st.session_state.segments = [{"index":i,"start":s['start'],"end":s['end'],"text":s['text']} for i,s in enumerate(asr.get('segments',[]))]
                    st.session_state.full_text = "".join([s['text']+" " for s in st.session_state.segments])
                    with st.spinner("分析角色..."):
                        df = extract_characters_silicon(st.session_state.full_text, model, api_key)
                        if df is not None:
                            host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                            st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                            st.success(f"听写成功！共 {len(st.session_state.segments)} 句。(音频模式)")

# 通用流程: 角色确认 -> 分镜
if st.session_state.char_df is not None:
    st.markdown("---")
    st.markdown("### 2. 确认角色 (强制注入生效中)")
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed")

    if st.button("🎬 3. 生成分镜 (双模通用)"):
        with st.spinner("设计分镜..."):
            char_names = st.session_state.char_df['name'].tolist()
            # 兼容两种模式的输入
            df = analyze_segments_or_text(st.session_state.segments, st.session_state.full_text, char_names, style, res_prompt, model, api_key)
            if df is not None:
                df = inject_character_prompts(df, st.session_state.char_df)
                st.session_state.shot_df = df
                st.success("分镜生成完毕！")

# 画图 & 下载
if st.session_state.shot_df is not None:
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, num_rows="dynamic", key="s_ed")
    st.markdown("---")
    c1, c2 = st.columns(2)
    
    if c1.button("🚀 4. 开始绘图"):
        bar = st.progress(0); log = st.empty(); tot = len(st.session_state.shot_df)
        for i, r in st.session_state.shot_df.iterrows():
            log.text(f"绘制 {i+1}/{tot}"); url = generate_image(r['final_prompt'], res_str, api_key)
            if "Error" not in url: st.session_state.gen_imgs[i] = url
            bar.progress((i+1)/tot)
            if i<tot-1: time.sleep(32)
        st.success("完成!")
        
    if c2.button("📦 5. 下载包"):
        if st.session_state.gen_imgs:
            st.download_button("⬇️ ZIP", create_zip(st.session_state.shot_df, st.session_state.gen_imgs).getvalue(), "project.zip", "application/zip")
        else: st.warning("先画图")
