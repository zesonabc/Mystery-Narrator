import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image

# ================= 配置区 =================
st.set_page_config(page_title="MysteryNarrator (标准版)", layout="wide", page_icon="🎬")

st.markdown("""
<style>
    .stApp { background-color: #0e0e0e; color: #fff; }
    .stButton>button { background-color: #e50914; color: white; border: none; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("⚙️ 设置")
    api_key = st.text_input("Gemini API Key", type="password")
    st.info("当前模式：标准免费版\n(Gemini 1.5 Flash + Imagen 3)")

# ================= 核心逻辑 =================
def analyze_script(script, key):
    genai.configure(api_key=key)
    
    # 1. 改用 Flash 模型 (免费版最稳的文本模型)
    # 既然 Pro 之前报错，我们退回到 Flash，它几乎兼容所有账号
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are a mystery movie director.
    Script: {script}
    Task: Split script into scenes. Determine if 'HOST' (talking) or 'SCENE' (visuals). Write an English Image Prompt.
    Style: Cinematic, horror, photorealistic, 80s film grain.
    Output JSON: [{{"script": "...", "type": "HOST/SCENE", "prompt": "..."}}]
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"文本分析失败 (Flash模型): {e}")
        return None

def generate_image(prompt, key):
    genai.configure(api_key=key)
    try:
        # 2. 改用标准 Imagen 3 (非付费版)
        model = genai.GenerativeModel('imagen-3.0-generate-001')
        
        result = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9"
        )
        return result.images[0]._pil_image
    except Exception as e:
        # 如果这里报错，说明你的免费账号连基础画图权限都没开通
        return f"Error: {e}"

# ================= 界面 =================
st.title("🎬 MysteryNarrator Standard")
st.caption("使用 Gemini 1.5 Flash (文本) + Imagen 3 (标准画图)")

text_input = st.text_area("输入解说词", height=100)

if st.button("🚀 生成分镜"):
    if not api_key:
        st.error("请填入 Key")
    else:
        with st.spinner("正在分析..."):
            scenes = analyze_script(text_input, api_key)
            
        if scenes:
            st.success(f"分析完成！共 {len(scenes)} 个镜头。开始画图...")
            
            # 创建容器显示结果
            result_container = st.container()
            progress = st.progress(0)
            
            for i, scene in enumerate(scenes):
                with result_container:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.markdown(f"**镜头 {i+1} [{scene['type']}]**")
                        st.write(scene['script'])
                        st.caption(scene['prompt'])
                    with c2:
                        # 实时画图
                        img_res = generate_image(scene['prompt'], api_key)
                        if isinstance(img_res, str): # 如果返回是字符串，说明是报错信息
                            st.warning("⚠️ 画图失败")
                            st.caption(f"原因: {img_res}")
                            if "404" in img_res or "Not Found" in img_res:
                                st.error("结论：你的免费账号暂无 API 画图权限。")
                        else:
                            st.image(img_res)
                st.divider()
                progress.progress((i + 1) / len(scenes))
