import streamlit as st
import requests
import pandas as pd
import json
import re
import time

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator - 悬疑解说助手 (V5.0)",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 悬疑黑红配色 CSS
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d; color: #c0c0c0; }
    [data-testid="stSidebar"] { background-color: #141414; border-right: 1px solid #222; }
    h1, h2, h3 { color: #d32f2f !important; font-family: sans-serif; font-weight: 700; }
    .stTextArea textarea, .stTextInput input, .stSelectbox div[data-testid="stSelectboxInner"] {
        background-color: #1e1e1e !important; color: #e0e0e0 !important; border: 1px solid #333 !important;
    }
    .stButton > button {
        background-color: #d32f2f; color: white; border: none; width: 100%; padding: 10px; font-weight: bold;
    }
    .stButton > button:hover { background-color: #b71c1c; }
    [data-testid="stDataFrame"] { border: 1px solid #333; }
    .stSuccess { background-color: #1b5e20 !important; color: #fff !important; }
    .stInfo { background-color: #0d47a1 !important; color: #fff !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心功能函数
# ==========================================

def get_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

def clean_json_text(text):
    # 清理 markdown
    text = re.sub(r'```json', '', text)
    text = re.sub(r'```', '', text)
    # 专门针对 DeepSeek R1 可能出现的 <think> 标签进行清理
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()

# --- 功能 A: 角色分析 ---
def extract_characters_silicon(script_text, model_choice, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    system_prompt = """
    你是一位悬疑片选角导演。请阅读文案，提取关键角色。
    要求：
    1. 必须包含 "博主" (Host)。
    2. 为每个角色生成英文外貌 Prompt (30词以内)。
    3. 输出纯 JSON 对象列表: [{"name": "博主", "prompt": "..."}, {"name": "受害者", "prompt": "..."}]
    """

    payload = {
        "model": model_choice, # 使用用户选择的模型
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.5,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=60)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            return pd.DataFrame(json.loads(clean_json_text(content)))
        else:
            st.error(f"角色分析失败: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {e}")
        return None

# --- 功能 B: 智能分镜分析 ---
def analyze_script_with_characters(script_text, character_data, style_desc, resolution_prompt, model_choice, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    char_prompt_list = ""
    for _, row in character_data.iterrows():
        char_prompt_list += f"- [{row['name']}]: {row['prompt']}\n"

    system_prompt = f"""
    你是一位悬疑电影导演。根据文案和角色表设计分镜。
    
    【角色表】
    {char_prompt_list}
    
    【风格与构图】
    - 风格: {style_desc}
    - 构图: {resolution_prompt} (优先使用远景 Long shot)
    
    【任务】
    1. 拆分为 3-6 秒的镜头。
    2. 类型(type): "CHARACTER"(有人) 或 "SCENE"(空镜)。
    3. 英文 Prompt (final_prompt): 
       - 必须包含构图词(Long shot等)。
       - 如涉及角色，必须复制角色表中的英文描述。
       - SCENE 镜头严禁出现人。

    【输出】纯 JSON 对象列表: "time", "script", "type", "visual_desc", "final_prompt"。
    """

    payload = {
        "model": model_choice, # 使用用户选择的模型
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=120)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            return pd.DataFrame(json.loads(clean_json_text(content)))
        else:
            st.error(f"分镜生成失败: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {e}")
        return None

# --- 功能 C: 图片生成 ---
def generate_image_kolors(prompt, resolution_str, api_key):
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    payload = {
        "model": "Kwai-Kolors/Kolors",
        "prompt": prompt,
        "image_size": resolution_str,
        "batch_size": 1
    }
    
    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=60)
        if response.status_code == 200:
            return response.json().get('data', [{}])[0].get('url')
        else:
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error: {str(e)}"

# ==========================================
# 3. 界面逻辑
# ==========================================

# 初始化
if 'character_df' not in st.session_state: st.session_state.character_df = None
if 'shot_list_df' not in st.session_state: st.session_state.shot_list_df = None

with st.sidebar:
    st.markdown("### 🔑 API 设置")
    api_key = st.text_input("SiliconFlow Key", type="password", help="sk-...")
    
    st.markdown("---")
    st.markdown("### 🧠 导演大脑 (模型选择)")
    # 这里是核心更新：让用户选模型
    model_choice = st.selectbox(
        "选择分析模型",
        (
            "Qwen/Qwen2.5-72B-Instruct", 
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1-Distill-Llama-70B" 
        ),
        index=0,
        help="推荐 Qwen 72B (稳) 或 DeepSeek V3 (强)"
    )
    
    st.markdown("---")
    st.markdown("### 📐 画面与风格")
    resolution_option = st.selectbox("画幅比例", ("电影宽屏 (16:9)", "标准横屏 (4:3)", "竖屏 (9:16)"), index=0)
    
    res_map = {
        "电影宽屏 (16:9)": ("1280x720", "Cinematic 16:9, wide screen"),
        "标准横屏 (4:3)": ("1024x768", "4:3 aspect ratio"),
        "竖屏 (9:16)": ("720x1280", "9:16 portrait")
    }
    resolution_str, resolution_prompt = res_map[resolution_option]

    default_style = """Film noir, suspense thriller, low key lighting, high contrast, gritty film grain, masterpiece."""
    visual_style = st.text_area("影调风格", value=default_style, height=100)

st.title("🕵️‍♂️ MysteryNarrator V5")
st.caption(f"当前大脑: {model_choice} | 当前画师: Kwai-Kolors")

# Step 1
st.markdown("### 📝 1. 输入文案")
script_input = st.text_area("解说词...", height=150)

# Step 2
st.markdown("---")
st.markdown("### 👥 2. 角色定妆")
if st.button("🔍 提取角色"):
    if not api_key: st.warning("请填 Key")
    elif not script_input: st.warning("请填文案")
    else:
        with st.spinner("正在分析角色..."):
            char_df = extract_characters_silicon(script_input, model_choice, api_key)
            if char_df is not None:
                st.session_state.character_df = char_df
                st.success("角色提取成功！")

if st.session_state.character_df is not None:
    edited_char_df = st.data_editor(st.session_state.character_df, num_rows="dynamic", key="char_edit")
    st.session_state.character_df = edited_char_df

# Step 3
st.markdown("---")
st.markdown("### 🎬 3. 生成分镜")
btn_disabled = st.session_state.character_df is None
if st.button("🧠 生成分镜表", disabled=btn_disabled):
    with st.spinner("导演正在设计镜头..."):
        shot_df = analyze_script_with_characters(
            script_input, st.session_state.character_df, visual_style, resolution_prompt, model_choice, api_key
        )
        if shot_df is not None:
            st.session_state.shot_list_df = shot_df
            st.success("分镜生成成功！")

if st.session_state.shot_list_df is not None:
    edited_shot_df = st.data_editor(st.session_state.shot_list_df, num_rows="dynamic", key="shot_edit")
    st.session_state.shot_list_df = edited_shot_df

    # Step 4
    st.markdown("---")
    st.markdown("### 🖼️ 4. 开始拍摄")
    if st.button("🚀 启动自动绘图"):
        log = st.container()
        cols = st.columns(3)
        total = len(edited_shot_df)
        bar = st.progress(0)
        
        for i, row in edited_shot_df.iterrows():
            with log: st.caption(f"正在绘制 [{i+1}/{total}]: {row['script'][:10]}...")
            url = generate_image_kolors(row['final_prompt'], resolution_str, api_key)
            
            if "Error" in url: st.error(f"失败: {url}")
            else:
                with cols[i%3]: st.image(url, caption=f"Shot {i+1}")
            
            bar.progress((i+1)/total)
            if i < total-1: time.sleep(32)
        st.success("杀青！")
