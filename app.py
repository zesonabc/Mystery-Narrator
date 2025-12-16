import streamlit as st
import requests
import pandas as pd
import json
import re
import time

# ==========================================
# 1. 页面配置与悬疑风格 CSS
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator - 悬疑解说助手 (硅基版)",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 保持你喜欢的黑红配色
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    [data-testid="stSidebar"] { background-color: #0e0e0e; border-right: 1px solid #333; }
    h1, h2, h3 { color: #ff3333 !important; font-family: 'Courier New', monospace; }
    .stTextArea textarea, .stTextInput input { background-color: #1a1a1a; color: #ffffff; border: 1px solid #444; }
    .stButton > button { background-color: #990000; color: white; border: none; width: 100%; font-weight: bold; }
    .stButton > button:hover { background-color: #cc0000; color: white; }
    [data-testid="stDataFrame"] { border: 1px solid #333; }
    hr { border-color: #333; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心功能函数 (对接 SiliconFlow)
# ==========================================

# 通用的请求头
def get_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

# --- 功能 A: 文案分析 (大脑) ---
# 我们使用硅基流动上免费/便宜的智能模型 (如 Qwen2.5-72B 或 DeepSeek)
def analyze_script_silicon(script_text, host_desc, style_desc, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    # 构造 Prompt
    system_prompt = f"""
    你是一位专业的悬疑电影解说视频导演。
    【任务】将解说文案拆分为分镜表。
    【输入】
    1. 博主形象: {host_desc}
    2. 画面风格: {style_desc}
    【规则】
    1. 按语速将文案拆分为 3-5 秒的镜头。
    2. 分类 (type): 
       - "HOST": 博主出镜（分析、提问、对话）。
       - "SCENE": 剧情画面（描述环境、物体、现场）。
    3. 画面描述 (visual_desc): 中文描述。
    4. 绘图提示词 (final_prompt): 英文 Prompt。
       - HOST: 包含博主形象 + 表情动作。
       - SCENE: 纯场景，不含博主，加入风格关键词。
    
    【必须输出纯 JSON 格式】：
    一个对象列表，字段包含: "time", "script", "type", "visual_desc", "final_prompt"。
    不要输出 markdown 代码块，直接输出 JSON 字符串。
    """

    payload = {
        "model": "Qwen/Qwen2.5-72B-Instruct", # 使用通义千问 72B (通常在硅基上是免费或极低成本且聪明的)
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"} # 强制 JSON 模式
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=60)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # 清洗一下以防万一
            content = re.sub(r'```json', '', content)
            content = re.sub(r'```', '', content)
            return pd.DataFrame(json.loads(content))
        else:
            st.error(f"分析失败: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {e}")
        return None

# --- 功能 B: 图片生成 (画师) ---
# 使用免费的 Kwai-Kolors
def generate_image_kolors(prompt, api_key):
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    payload = {
        "model": "Kwai-Kolors/Kolors", # 免费神器
        "prompt": prompt,
        "image_size": "1024x1024",
        "batch_size": 1
    }
    
    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=60)
        if response.status_code == 200:
            return response.json().get('data', [{}])[0].get('url')
        else:
            return f"Error: {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"

# ==========================================
# 3. 界面逻辑
# ==========================================

with st.sidebar:
    st.markdown("## ⚙️ 硅基流动设置")
    api_key = st.text_input("SiliconFlow Key (sk-...)", type="password", value="")
    
    st.markdown("---")
    st.markdown("### 🕵️ 博主设定")
    default_host = "A 30-year-old Asian man, wearing a green cap and brown leather jacket, stubble beard, looking at the viewer, dramatic lighting."
    host_persona = st.text_area("形象 Prompt", value=default_host, height=100)
    
    st.markdown("### 🎨 风格设定")
    default_style = "Cinematic, horror movie style, 80s retro film grain, high contrast, dim lighting, photorealistic."
    visual_style = st.text_area("风格 Prompt", value=default_style, height=80)
    
    st.info("💡 当前模型配置：\n- 大脑: Qwen2.5-72B\n- 画师: Kwai-Kolors (免费)")

st.title("🔪 MysteryNarrator (SiliconFlow版)")
st.caption("悬疑解说可视化助手 | 真正的 [免费生图] 工作流")

# --- Step 1: 输入 ---
st.markdown("### Step 1: 输入解说词")
script_input = st.text_area("粘贴文案...", height=150)

if 'shot_list_df' not in st.session_state:
    st.session_state.shot_list_df = None

# --- Step 2: 分析 ---
if st.button("🎬 1. AI 拆解分镜"):
    if not api_key:
        st.warning("请先在左侧填入 Key！")
    elif not script_input:
        st.warning("没文案怎么拆？")
    else:
        with st.spinner("🕵️‍♂️ 正在调用 Qwen 模型分析剧本..."):
            df = analyze_script_silicon(script_input, host_persona, visual_style, api_key)
            if df is not None:
                st.session_state.shot_list_df = df
                st.success("拆解完成！请在下方核对。")

# --- Step 3: 核对 ---
if st.session_state.shot_list_df is not None:
    st.markdown("---")
    st.markdown("### Step 2: 核对分镜表")
    
    edited_df = st.data_editor(
        st.session_state.shot_list_df,
        column_config={
            "type": st.column_config.SelectboxColumn("Type", options=["HOST", "SCENE"], width="small"),
            "final_prompt": st.column_config.TextColumn("Prompt (可修改)", width="large"),
            "visual_desc": st.column_config.TextColumn("中文描述", width="medium"),
        },
        use_container_width=True,
        num_rows="dynamic"
    )
    
    st.session_state.shot_list_df = edited_df

    # --- Step 4: 真实生成 ---
    st.markdown("---")
    st.markdown("### Step 3: 开始生产 (Production)")
    
    st.warning("⚠️ 注意：Kolors 免费版限制每分钟约 2 张图。我们会自动控制速度，请耐心等待。")
    
    if st.button("🖼️ 启动自动绘图机 (真实生成)"):
        st.markdown("#### 🚀 生成日志")
        log_container = st.container()
        gallery_cols = st.columns(4) # 图片展示区
        
        total = len(edited_df)
        progress_bar = st.progress(0)
        
        generated_images = []
        
        for index, row in edited_df.iterrows():
            with log_container:
                st.write(f"👉 [{index+1}/{total}] 正在生成: {row['script'][:20]}...")
            
            # 调用生图函数
            image_url = generate_image_kolors(row['final_prompt'], api_key)
            
            if "Error" in image_url:
                st.error(f"第 {index+1} 张生成失败: {image_url}")
            else:
                generated_images.append(image_url)
                # 实时显示在下面
                with gallery_cols[index % 4]:
                    st.image(image_url, caption=f"Shot {index+1}", use_column_width=True)
                    st.markdown(f"[下载]({image_url})")
            
            progress_bar.progress((index + 1) / total)
            
            # 【关键】强制休息，防止被封 IP
            # Kolors 限制每分钟 2 张 -> 每张间隔 30秒
            if index < total - 1:
                with log_container:
                    st.info("☕ 喝口水，冷却 30 秒以防超速...")
                time.sleep(32) 
        
        st.success("✅ 全部任务结束！")
