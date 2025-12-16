import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import time
from PIL import Image

# ================= 配置区 =================
st.set_page_config(page_title="MysteryNarrator (Auto-Fix)", layout="wide", page_icon="🛡️")

st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .stButton>button { background-color: #2E8B57; color: white; border: none; font-weight: bold; }
    .status-box { padding: 10px; border-radius: 5px; margin-bottom: 10px; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🛡️ 自动修复引擎")
    api_key = st.text_input("Gemini API Key", type="password")
    st.info("原理：自动寻找你账号里【真正免费】的模型，跳过付费陷阱。")

# ================= 核心逻辑：打不死的小强 =================

def get_working_text_model(key):
    """ 自动寻找可用的文本模型 """
    genai.configure(api_key=key)
    
    # 优先级列表：先试 2.0 (新且免费)，再试 1.5 (稳)，最后试 Flash
    # 绝对不试 gemini-3，因为那个要钱
    candidates = [
        "gemini-2.0-flash-exp", 
        "gemini-1.5-pro", 
        "gemini-1.5-flash",
        "gemini-1.0-pro"
    ]
    
    status_text = st.empty()
    
    for model_name in candidates:
        try:
            status_text.text(f"正在尝试连接: {model_name} ...")
            model = genai.GenerativeModel(model_name)
            # 发送一个极简的测试请求
            response = model.generate_content("Hi", request_options={"timeout": 5})
            status_text.empty()
            return model_name # 成功！返回这个能用的名字
        except Exception as e:
            # 失败了？没关系，试下一个
            print(f"{model_name} 不可用: {e}")
            continue
            
    return None

def analyze_script(script, key):
    # 1. 先找个能用的模型
    valid_model_name = get_working_text_model(key)
    
    if not valid_model_name:
        st.error("❌ 你的 Key 似乎无法连接任何免费模型。请检查 Key 是否已被封禁。")
        return None
        
    st.toast(f"已连接模型: {valid_model_name}")
    
    # 2. 开始干活
    model = genai.GenerativeModel(valid_model_name)
    prompt = f"""
    You are a mystery video director.
    Script: {script}
    Task: Split script into scenes. Write an Image Prompt for Imagen 3.
    Output JSON: [{{"script": "...", "prompt": "..."}}]
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"分析失败: {e}")
        return None

def generate_image(prompt, key):
    genai.configure(api_key=key)
    
    # 只尝试标准 Imagen 3，这是目前唯一的免费画图通道
    # 如果这个报错，说明账号真没画图权限
    target_model = 'imagen-3.0-generate-001'
    
    try:
        model = genai.GenerativeModel(target_model)
        result = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9"
        )
        return result.images[0]._pil_image
    except Exception as e:
        return f"画图失败 ({str(e)})"

# ================= 主界面 =================
st.title("🎬 MysteryNarrator (Auto-Fix)")
st.caption("不再报错版：自动匹配可用模型")

text_input = st.text_area("输入解说词", height=100)

if st.button("🚀 启动"):
    if not api_key:
        st.error("请填入 Key")
    else:
        with st.spinner("🤖 正在为您寻找免费通道..."):
            scenes = analyze_script(text_input, api_key)
            
        if scenes:
            st.success(f"分析成功！开始画图...")
            
            result_container = st.container()
            
            for i, scene in enumerate(scenes):
                with result_container:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.markdown(f"**#{i+1}**")
                        st.write(scene['script'])
                        st.caption(scene['prompt'])
                    with c2:
                        img_res = generate_image(scene['prompt'], api_key)
                        if isinstance(img_res, str):
                            # 画图失败不报错红字，而是显示优雅的提示
                            st.warning("⚠️ 暂无图像")
                            st.caption(f"原因: {img_res[:100]}...") # 只显示前100字
                        else:
                            st.image(img_res)
                st.divider()
