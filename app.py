import streamlit as st
import requests
import json

st.set_page_config(page_title="API 验尸官", layout="wide", page_icon="⚖️")
st.markdown("""<style>.stApp { background-color: #000; color: #fff; }</style>""", unsafe_allow_html=True)

st.title("⚖️ API 请求死因分析")
st.warning("我们将直接向 Google 发送 HTTP 请求，并展示服务器返回的原始拒绝理由。")

api_key = st.text_input("请输入 Gemini API Key", type="password")

def test_model_http(model_id, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:predict?key={key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "instances": [{"prompt": "A banana on a table"}],
        "parameters": {"sampleCount": 1}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        return response.status_code, response.text
    except Exception as e:
        return 0, str(e)

if st.button("🚨 开始侦查"):
    if not api_key:
        st.error("没填 Key")
    else:
        # 我们测试三个最可能的嫌疑人
        suspects = [
            "imagen-3.0-generate-001",   # 标准版
            "gemini-2.5-flash-image",    # Nano Banana
            "imagen-4.0-generate-001"    # Imagen 4
        ]
        
        for model in suspects:
            st.markdown(f"### 🔫 测试目标: `{model}`")
            code, text = test_model_http(model, api_key)
            
            if code == 200:
                st.success(f"🎉 奇迹发生了！这个模型可以用！")
                st.image("https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif", width=200)
            else:
                st.error(f"❌ 失败 (状态码: {code})")
                st.markdown("**Google 官方拒绝理由:**")
                # 这是一个黑色的代码框，里面的内容至关重要
                st.code(text, language="json")
            
            st.divider()
