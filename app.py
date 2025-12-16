import streamlit as st
import requests
import json

st.set_page_config(page_title="硅基流动 API 测试台", layout="wide", page_icon="🚀")

st.title("🚀 硅基流动 (SiliconFlow) 连通性测试")
st.markdown("这个工具用于测试你的 Key 能否成功调用免费的画图模型。")

# 你的 Key (sk- 开头)
api_key = st.text_input("请输入你的 SiliconFlow API Key (sk-...)", type="password")

def test_siliconflow(model_name, key):
    # 硅基流动的标准画图接口地址
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"  # 必须带上 Bearer
    }
    
    # 硅基流动要求的标准发送格式
    data = {
        "model": model_name,
        "prompt": "A cute cyberpunk cat, cinematic lighting, high quality", # 测试提示词
        "image_size": "1024x1024",
        "batch_size": 1
    }
    
    try:
        with st.spinner(f"正在呼叫 {model_name} ..."):
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
        if response.status_code == 200:
            # 成功！解析返回的图片地址
            res_json = response.json()
            # 通常图片地址在 data[0].url 里
            image_url = res_json.get('data', [{}])[0].get('url')
            return True, image_url, response.text
        else:
            return False, None, response.text
            
    except Exception as e:
        return False, None, str(e)

if st.button("⚡ 开始测试"):
    if not api_key:
        st.error("请先填入 Key！")
    else:
        # 我们测试两个最适合你的模型：免费的 Kolors 和 便宜快读的 Flux
        targets = [
            "Kwai-Kolors/Kolors",             # 【重点】快手可图（免费，懂中文）
            "black-forest-labs/FLUX.1-schnell" # Flux 极速版（免费/极低成本）
        ]
        
        cols = st.columns(len(targets))
        
        for i, model in enumerate(targets):
            with cols[i]:
                st.subheader(f"测试模型: {model}")
                success, img_url, raw_log = test_siliconflow(model, api_key)
                
                if success:
                    st.success("✅ 调用成功！")
                    st.image(img_url, caption="刚刚生成的测试图", use_column_width=True)
                    st.markdown(f"[点击查看原图]({img_url})")
                else:
                    st.error("❌ 调用失败")
                    st.markdown("**错误日志:**")
                    st.code(raw_log, language="json")

st.divider()
st.info("💡 提示：如果 Kolors 测试成功，你就可以放心地去写那个小说转视频的脚本了！")
