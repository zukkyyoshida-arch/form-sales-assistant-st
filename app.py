import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import os

# --- 設定 ---
st.set_page_config(page_title="Form Sales Assistant", page_icon="📝", layout="centered")

st.title("📝 Form Sales Assistant")
st.markdown("AIを活用したパーソナライズ営業文面ジェネレーター")

# APIキーの取得 (Streamlit Secrets または 環境変数)
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ GEMINI_API_KEY が設定されていません。Streamlit CloudのSecretsに設定してください。")
    st.stop()

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

def scrape_url(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 不要なタグを削除
        for script in soup(["script", "style", "noscript", "iframe", "img", "svg"]):
            script.decompose()
            
        text = soup.get_text(separator=' ', strip=True)
        # トークン制限対策として先頭10000文字に制限
        return text[:10000]
    except Exception as e:
        st.warning(f"URLの取得に失敗しました ({url}): {e}")
        return None

# --- UI ---
st.write("対象企業の参考URL（コーポレートサイト、採用ページ等）を入力してください。（最大5個）")

if "url_count" not in st.session_state:
    st.session_state.url_count = 1

urls = []
for i in range(st.session_state.url_count):
    url = st.text_input(f"参考URL {i+1}", key=f"url_{i}")
    if url.strip():
        urls.append(url.strip())

if st.session_state.url_count < 5:
    if st.button("➕ URLを追加", key="add_url_btn"):
        st.session_state.url_count += 1
        st.rerun()

if st.button("分析＆文面生成", type="primary"):
    if not urls:
        st.error("少なくとも1つの有効なURLを入力してください。")
    else:
        with st.spinner("サイトから情報を取得し、AIで分析・文面生成を行っています..."):
            texts = []
            for url in urls:
                text = scrape_url(url)
                if text:
                    texts.append(text)
            
            if not texts:
                st.error("有効なテキスト情報が取得できませんでした。")
                st.stop()
            
            combined_text = "\n\n--- 次のページ ---\n\n".join(texts)
            
            prompt = f"""
あなたは非常に優秀なBtoB営業・マーケティングのコンサルタントです。
以下のウェブサイト情報を読み込み、対象企業を特定した上で、指示に従ってJSON形式で結果を出力してください。

【対象企業のウェブサイト情報】
{combined_text}

【タスク1：企業分析】
対象企業について、以下の5つの観点で情報を整理してください。
①事業の強み
②現在力を入れていそうな領域
③直近のニュースやプレスリリースがあれば内容（なければ「特になし」）
④採用ページなどから推測される組織課題
⑤この会社が今抱えていそうなマーケティング課題

【タスク2：フォーム営業の文面作成】
上記の分析結果を踏まえて、この会社「専用」のフォーム営業の文面を作成してください。
以下のルールを厳格に守ること。
【ルール】
・「非常に優秀なトップ営業マン」として、人間らしく自然で、少しだけカジュアルな親しみやすいトーンで書くこと。
・「拝見しました」「大変関心を抱きました」「確信しております」「貴社のご発展に〜」「突然のご連絡失礼いたします」などの業者っぽい硬い敬語や定型句は絶対に使わない（禁止）。
・代わりに「〜のリリース、思わず見入ってしまいました！」「〜というビジョン、すごく共感します！」など、自然な感情表現を使うこと。
・構成は以下の順序にすること。
  1. パーソナライズされた導入（相手の最新ニュースや強みをフックにした自然な声かけ）
  2. 課題への寄り添い（「〇〇を立ち上げた今、〜といった壁があるのではないでしょうか？」と推測する）
  3. 自社の提案（「弊社はWeb集客を得意としており、〇〇の領域でお手伝いできるかもしれないと思い〜」など超短く柔らかく提案。自社の機能説明ばかりにならないように）
  4. カジュアルなクロージング（「もし少しでもご興味があれば、まずは情報交換からでもいかがでしょうか？」など）
・適度に改行を入れ、文字数は250〜350文字程度で、スマートフォンでも読みやすくすること。

出力は必ず以下のJSONスキーマに従ってください。JSON以外のテキスト（マークダウンのバッククォートなど）は出力しないでください。

{{
  "analysis": {{
    "strengths": "①事業の強み",
    "focusAreas": "②現在力を入れていそうな領域",
    "news": "③直近のニュースやプレスリリース",
    "orgIssues": "④推測される組織課題",
    "marketingIssues": "⑤抱えていそうなマーケティング課題"
  }},
  "draft": "生成されたフォーム営業文面"
}}
"""
            
            try:
                # generate_content with application/json requirement
                # To ensure valid JSON output, we can use generation_config
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                    )
                )
                
                result_text = response.text
                result = json.loads(result_text)
                
                st.success("生成が完了しました！")
                
                st.subheader("📊 企業分析結果")
                analysis = result.get("analysis", {})
                st.markdown(f"**① 事業の強み:**\n{analysis.get('strengths', '')}")
                st.markdown(f"**② 現在力を入れていそうな領域:**\n{analysis.get('focusAreas', '')}")
                st.markdown(f"**③ 直近のニュース/PR:**\n{analysis.get('news', '')}")
                st.markdown(f"**④ 推測される組織課題:**\n{analysis.get('orgIssues', '')}")
                st.markdown(f"**⑤ 抱えていそうなマーケ課題:**\n{analysis.get('marketingIssues', '')}")
                
                st.subheader("✉️ 生成されたドラフト")
                st.info("AIが作成した文面です。「最後の1行」をあなたの言葉で追記して、よりパーソナライズされた文面に仕上げましょう。")
                draft = result.get("draft", "")
                st.text_area("ドラフト文面", draft, height=200)
                
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
