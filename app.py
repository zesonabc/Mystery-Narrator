import streamlit as st
import requests
import pandas as pd
import json
import re
import time

# ==========================================
# 1. 页面配置 (Page Config)
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator - 悬疑解说助手 (远景版)",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 样式优化：黑/红/白 悬疑配色
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

def get_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

# --- 功能 A: 智能分镜分析 (大脑) ---
def analyze_script_silicon(script_text, host_desc, style_desc, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    # 核心指令升级：强制远景 + 角色固定
    system_prompt = f"""
    你是一位专业的悬疑电影解说视频导演。
    【任务】将解说文案拆分为分镜表。
    
    【全局约束 - 必须严格遵守】
    1. **景别锁定 (Shot Size)**: 所有画面必须使用【远景】(Long Shot) 或 【广角】(Wide Angle)，展现环境氛围，严禁使用特写(Close up)。
    2. **角色一致性 (Consistency)**: 对于 "HOST" 类型的镜头，必须严格包含博主的外貌描述。
    
    【输入信息】
    1. 博主形象 (Host Persona): {host_desc}
    2. 画面风格 (Style): {style_desc}
    
    【处理逻辑】
    1. 将文案拆分为 3-5 秒的镜头。
    2. 分类 (type): 
       - "HOST": 博主出镜（分析、提问）。
       - "SCENE": 剧情画面（环境、凶案现场）。
    3. 编写英文 Prompt (final_prompt):
       - 格式要求: "Long shot, Wide angle, [环境描述], [角色描述(如果是HOST)], [光影风格], masterpiece, 8k"
       - 如果是 HOST: 必须包含 "{host_desc}"。
       - 如果是 SCENE: 必须不包含博主，只描述环境。
    
    【输出格式】
    请仅输出纯 JSON 格式的对象列表，包含: "time", "script", "type", "visual_desc", "final_prompt"。
    """

    payload = {
        "model": "Qwen/Qwen2.5-72B-Instruct", # 聪明的大脑
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=60)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # 清理 Markdown 标记
            content = re.sub(r'```json', '', content)
            content = re.sub(r'```', '', content)
            return pd.DataFrame(json.loads(content))
        else:
            st.error(f"分析失败: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {e}")
        return None

# --- 功能 B: 图片生成 (画师 - 宽屏版) ---
def generate_image_kolors(prompt, resolution, api_key):
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    payload = {
        "model": "Kwai-Kolors/Kolors", # 免费可图
        "prompt": prompt,
        "image_size": resolution,      # 这里调用你选择的分辨率 (如 1280x720)
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
# 3. 界面逻辑 (UI)
# ==========================================

with st.sidebar:
    st.markdown("## ⚙️ 设置")
    api_key = st.text_input("SiliconFlow Key (sk-...)", type="password", help="去硅基流动后台获取")
    
    st.markdown("---")
    st.markdown("### 📐 画面设置")
    # 这里增加了分辨率选择，默认设为 1280x720
    resolution = st.selectbox(
        "选择分辨率 (Resolution)",
        ["1280x720", "1024x1024", "720x1280"],
        index=0,
        help="推荐使用 1280x720 (16:9 横屏电影感)"
    )
    
    st.markdown("---")
    st.markdown("### 🕵️ 固定博主形象")
    # 默认词里加了 full body shot (全身/远景) 以防万一
    default_host = "A 30-year-old Asian man, wearing a green cap and brown leather jacket, stubble beard, looking at the viewer, full body shot, distance shot."
    host_persona = st.text_area("人物提示词 (Prompt)", value=default_host, height=120)
    
    st.markdown("### 🎨 统一画风")
    default_style = "Cinematic, horror movie style, 80s retro film grain, high contrast, dim lighting, wide angle lens."
    visual_style = st.text_area("环境风格 (Prompt)", value=default_style, height=80)

st.title("🎬 MysteryNarrator (宽屏远景版)")
st.caption("硅基流动免费版 | 强制 16:9 | 强制远景 | 角色固定")

# --- Step 1: 输入 ---
st.markdown("### Step 1: 输入解说词")
script_input = st.text_area("粘贴文案...", height=150, placeholder="男人走进废弃的医院，走廊尽头似乎有人影...")

if 'shot_list_df' not in st.session_state:
    st.session_state.shot_list_df = None

# --- Step 2: 分析 ---
if st.button("🧠 1. AI 拆解分镜"):
    if not api_key:
        st.warning("请在左侧填入 Key！")
    elif not script_input:
        st.warning("请输入文案")
    else:
        with st.spinner("🕵️‍♂️ 导演正在安排远景机位..."):
            df = analyze_script_silicon(script_input, host_persona, visual_style, api_key)
            if df is not None:
                st.session_state.shot_list_df = df
                st.success("分镜已生成！所有镜头已强制设为远景模式。")

# --- Step 3: 核对与生成 ---
if st.session_state.shot_list_df is not None:
    st.markdown("---")
    st.markdown("### Step 2: 核对分镜表")
    
    edited_df = st.data_editor(
        st.session_state.shot_list_df,
        column_config={
            "type": st.column_config.SelectboxColumn("类型", options=["HOST", "SCENE"], width="small"),
            "final_prompt": st.column_config.TextColumn("英文指令 (含远景词)", width="large"),
            "visual_desc": st.column_config.TextColumn("中文描述", width="medium"),
            "time": st.column_config.TextColumn("时长", width="small")
        },
        use_container_width=True,
        num_rows="dynamic"
    )
    
    st.session_state.shot_list_df = edited_df

    st.markdown("---")
    st.markdown("### Step 3: 开始生产")
    st.info(f"当前分辨率: **{resolution}** | 速度限制: 每分钟约 2 张 (防止封号)")
    
    if st.button("🖼️ 启动绘图 (宽屏模式)"):
        st.markdown("#### 🚀 生成进度")
        log_container = st.container()
        gallery_cols = st.columns(3) # 宽屏图，每行放3张比较好看
        
        total = len(edited_df)
        progress_bar = st.progress(0)
        
        for index, row in edited_df.iterrows():
            # 1. 显示日志
            with log_container:
                st.caption(f"[{index+1}/{total}] 正在绘制: {row['script'][:15]}...")
            
            # 2. 调用 API
            image_url = generate_image_kolors(row['final_prompt'], resolution, api_key)
            
            # 3. 处理结果
            if "Error" in image_url:
                st.error(f"第 {index+1} 张失败: {image_url}")
            else:
                # 成功显示
                with gallery_cols[index % 3]:
                    st.image(image_url, caption=f"Shot {index+1}", use_column_width=True)
                    st.markdown(f"[下载原图]({image_url})")
            
            # 4. 进度条
            progress_bar.progress((index + 1) / total)
            
            # 5. 强制冷却 (Kolors 免费版限制)
            if index < total - 1:
                time.sleep(32) 
        
        st.success("✅ 全部生成完毕！")
