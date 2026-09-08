import os
import json
import time
import io
import re
import threading
import gc
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Load environment variables from .env if present
load_dotenv()

class DriveGeminiService:
    def __init__(self):
        self.drive_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        
        # Cache variables and lock
        self._pdf_cache: List[Dict[str, Any]] = []
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 1200.0  # 20 minutes cache TTL
        self._lock = threading.Lock()
        
        # Configure Gemini API if key exists
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)

    def _get_drive_service(self):
        """Initialize and return Google Drive API service client."""
        if not self.service_account_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON 環境変数が設定されていません。")
        
        try:
            raw = self.service_account_json.strip()
            if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
                raw = raw[1:-1].strip()

            info = json.loads(raw)
            if isinstance(info, dict) and "private_key" in info:
                pk = info["private_key"]
                if "\\n" in pk:
                    info["private_key"] = pk.replace("\\n", "\n")

            scopes = ['https://www.googleapis.com/auth/drive.readonly']
            credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
            return build('drive', 'v3', credentials=credentials)
        except Exception as e:
            print(f"[DriveGeminiService] Auth Exception: {e}")
            raise RuntimeError(f"Google Drive サービスアカウントの認証失敗: {str(e)}")

    def _download_single_pdf(self, service, f) -> Dict[str, Any]:
        """Download and extract a single PDF file with safe error isolation."""
        file_id = f['id']
        file_name = f['name']
        try:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            fh.seek(0)
            pdf_bytes = fh.read()

            # Skip oversized files (>15MB) to keep memory safe
            if len(pdf_bytes) > 15 * 1024 * 1024:
                print(f"[DriveGeminiService] Skipping large PDF ({len(pdf_bytes)} bytes): {file_name}")
                return {'id': file_id, 'name': file_name, 'text': f"[{file_name} は大容量のためスキップ]"}

            extracted_text = self._extract_pdf_text(pdf_bytes, file_name)
            
            # Immediately release heavy binary bytes
            del pdf_bytes
            fh.close()
            gc.collect()

            return {
                'id': file_id,
                'name': file_name,
                'text': extracted_text
            }
        except Exception as e:
            print(f"[DriveGeminiService] Safe skip for {file_name}: {e}")
            return {'id': file_id, 'name': file_name, 'text': f"[{file_name} 読み込みスキップ]"}

    def fetch_all_pdfs(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch all PDF files from target folder safely.
        """
        with self._lock:
            now = time.time()
            if not force_refresh and self._pdf_cache and (now - self._cache_timestamp < self._cache_ttl):
                return self._pdf_cache

            if not self.drive_folder_id or not self.service_account_json:
                return self._get_fallback_pdfs()

            t_start = time.time()
            try:
                service = self._get_drive_service()
                query = f"'{self.drive_folder_id}' in parents and mimeType='application/pdf' and trashed=false"
                results = service.files().list(q=query, fields="files(id, name)", pageSize=10, orderBy="modifiedTime desc").execute()
                files = results.get('files', [])

                if not files:
                    return self._get_fallback_pdfs()

                print(f"[DriveGeminiService] Fetching {len(files)} PDFs (Safe mode)...")
                loaded_pdfs = []
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(self._download_single_pdf, service, f) for f in files]
                    for future in as_completed(futures):
                        res = future.result()
                        if res:
                            loaded_pdfs.append(res)

                if loaded_pdfs:
                    self._pdf_cache = loaded_pdfs
                    self._cache_timestamp = now
                    t_end = time.time()
                    print(f"[DriveGeminiService] All {len(loaded_pdfs)} PDFs loaded & cached in {t_end - t_start:.2f}s!")
                    return loaded_pdfs
                else:
                    return self._get_fallback_pdfs()

            except Exception as e:
                print(f"[DriveGeminiService] Failed to load PDFs: {e}")
                return self._get_fallback_pdfs()

    def _extract_pdf_text(self, pdf_bytes: bytes, file_name: str) -> str:
        """Helper to extract plain text from PDF bytes using pypdf safely."""
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes), strict=False)
            text_pages = []
            for idx, page in enumerate(reader.pages):
                try:
                    extracted = page.extract_text() or ""
                    if extracted.strip():
                        text_pages.append(f"--- Page {idx+1} ---\n{extracted}")
                except Exception as page_e:
                    print(f"Page {idx+1} skipped in {file_name}: {page_e}")
                    continue
            return "\n".join(text_pages) if text_pages else f"[{file_name} のテキスト抽出なし]"
        except Exception as e:
            print(f"pypdf extraction skipped for {file_name}: {e}")
            return f"[{file_name} のテキスト抽出なし]"


    def _get_fallback_pdfs(self) -> List[Dict[str, Any]]:
        """Fallback demo documents when Drive API is not connected."""
        return [
            {
                'id': 'demo-1',
                'name': 'サイバーセキュリティ＆夢カワイイ運用ガイド.pdf',
                'text': """
                [資料1: サイバーセキュリティ＆原宿ゆめかわいい運用規定]
                第1条（目的）: 本アプリは、サイバー空間の厳重なセキュリティ認証と、ユーザーを癒すゆめかわいいUXを融合した高度認証Q&Aシステムである。
                第2条（認証コード）: システムアクセスに必要なコードは暗証キー（デフォルト: CYBER_SECRET_2026）である。認証失敗時はサイバー警告を発する。
                第3条（PDF横断解析）: Google Drive内の全PDFをコンテキストとしてGemini APIが自動解析し、文字数制限内で回答を生成する。
                """
            },
            {
                'id': 'demo-2',
                'name': '原宿魔法少女Q&Aマニュアル.pdf',
                'text': """
                [資料2: 原宿パステル魔法マニュアル]
                ・ゆめかわいい世界観では、ミルキーピンク(#FFDBE5)、パステルラベンダー(#E8D5FF)、ミントグリーン(#D0F4DE)を基調とする。
                ・Geminiちゃんはユーザーの質問に対して、ドライブ内のPDFをすみずみまで参照し、正確かつ可愛く簡潔に答える魔法を持つ。
                ・文字数指定（10〜1000文字）は絶対厳守であり、文末が途切れずに自然な日本語で締めくくられる。
                """
            }
        ]

    def _filter_relevant_docs(self, pdfs: List[Dict[str, Any]], question: str, max_docs: int = 10) -> List[Dict[str, Any]]:
        """Filter and rank relevant PDF documents using multi-keyword and fuzzy match scoring."""
        if len(pdfs) <= max_docs:
            return pdfs

        raw_words = [w.strip() for w in re.split(r'[\s,、。！？!?\n\t]+', question) if len(w.strip()) > 1]
        if not raw_words:
            return pdfs[:max_docs]

        scored_pdfs = []
        for pdf in pdfs:
            text = pdf.get('text', '')
            name = pdf.get('name', '')
            score = 0
            for w in raw_words:
                score += text.count(w) * 3
                score += name.count(w) * 15
            
            if len(text) > 200:
                score += 1

            scored_pdfs.append((score, pdf))

        scored_pdfs.sort(key=lambda x: x[0], reverse=True)
        top_matched = [pdf for score, pdf in scored_pdfs if score > 0]
        
        if top_matched:
            return top_matched[:max_docs]
        else:
            return pdfs[:max_docs]

    def ask_gemini(self, question: str, max_chars: int = 300) -> Dict[str, Any]:
        """
        Query Gemini model using PDF files/texts from Drive with high-precision system prompt.
        """
        if not self.gemini_api_key:
            mock_answer = self._generate_mock_answer(question, max_chars)
            return {
                "answer": mock_answer,
                "char_count": len(mock_answer),
                "max_chars": max_chars,
                "document_count": len(self.fetch_all_pdfs()),
                "sources": [doc["name"] for doc in self.fetch_all_pdfs()],
                "is_mock": True
            }

        all_pdfs = self.fetch_all_pdfs()

        # Match top 10 relevant PDFs for ultra-fast response
        pdfs = self._filter_relevant_docs(all_pdfs, question, max_docs=10)
        print(f"[DriveGeminiService] Precision search: using top {len(pdfs)} docs out of {len(all_pdfs)} total PDFs")


        # Build detailed text context from selected PDFs
        context_blocks = []
        fallback_pdf_parts = []

        for pdf in pdfs:
            doc_name = pdf['name']
            doc_text = pdf.get('text', '').strip()
            pdf_bytes = pdf.get('bytes')
            
            if doc_text and not doc_text.startswith("[テキスト抽出なし]"):
                context_blocks.append(f"=== 資料名: {doc_name} ===\n{doc_text}\n")
            elif pdf_bytes:
                fallback_pdf_parts.append(f"=== PDF添付資料: {doc_name} ===")
                fallback_pdf_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})

        full_context = "\n\n".join(context_blocks)

        system_instruction = (
            "あなたはGoogle Driveの複数PDF資料を横断解析する【超高度AIアナリスト】です。\n\n"
            "【回答生成の絶対ルール】\n"
            "1. 【資料の網羅的参照】提供された資料群の内容を多角的に分析し、質問に対して最も事実に基づいた正確で論理的な回答を作成してください。\n"
            "2. 【文字数の最大活用】指定された上限文字数（" + str(max_chars) + "文字）に対し、その80%〜100%（約" + str(int(max_chars * 0.8)) + "〜" + str(max_chars) + "文字）に達するよう、資料の背景、具体的根拠、詳細な説明を豊富に盛り込んで長文で詳しく記述してください。\n"
            "3. 【文章の完結】文章は絶対に途中で途切れさせず、必ず最後の句読点（。）まで自然で美しい日本語で書ききってください。\n"
            "4. 【洗練された表現】「資料によると」などの前置きは省き、見やすく分かりやすく構成してください。"
        )

        user_prompt_text = (
            f"【参照PDF資料データベース】\n{full_context}\n\n"
            f"【ユーザーからの質問】\n{question}\n\n"
            f"【指示】\n上記PDF資料の内容に基づき、指定文字数（{max_chars}文字以内、目標: {int(max_chars*0.8)}〜{max_chars}文字）をしっかり使って、途中で途切れることなく【最後の句読点（。）まで】詳しくボリューミーに解説した日本語で回答してください。"
        )


        if fallback_pdf_parts:
            gemini_payload = [user_prompt_text] + fallback_pdf_parts
        else:
            gemini_payload = user_prompt_text

        try:
            candidate_names = [
                "gemini-1.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-pro",
                "gemini-2.5-flash",
                "gemini-3.6-flash",
                "gemini-1.5-flash-latest",
                "gemini-pro-latest"
            ]

            response = None
            last_err = None
            used_model_name = ""

            for name in candidate_names:
                try:
                    model = genai.GenerativeModel(
                        model_name=name,
                        system_instruction=system_instruction
                    )
                    print(f"[DriveGeminiService] High-precision query on model: {name}")
                    res = model.generate_content(
                        gemini_payload,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.2,  # Low temperature for exact factuality
                            max_output_tokens=3000
                        )
                    )
                    if res and res.text:
                        response = res
                        used_model_name = name
                        print(f"[DriveGeminiService] High-precision answer generated via {name}")
                        break
                except Exception as e:
                    print(f"[DriveGeminiService] Candidate model '{name}' error: {e}")
                    last_err = e
                    continue

            if not response:
                raise RuntimeError(f"Geminiモデルでの回答生成に失敗しました: {last_err}")


            raw_answer = response.text.strip()
            
            # Post-processing enforcement of character count safety
            final_answer = self._enforce_character_limit(raw_answer, max_chars)

            return {
                "answer": final_answer,
                "char_count": len(final_answer),
                "max_chars": max_chars,
                "document_count": len(pdfs),
                "sources": [pdf["name"] for pdf in pdfs],
                "is_mock": False
            }

        except Exception as e:
            print(f"Gemini API Exception: {e}")
            err_str = str(e)
            if "404" in err_str or "not found" in err_str:
                fallback_msg = (
                    "【APIキー設定エラー】\n"
                    "Google AI Studioの有効なAPIキーが設定されていない可能性があります。\n"
                    "Google AI Studio (https://aistudio.google.com/) で発行した「AIzaSy」から始まるAPIキーを .env の GEMINI_API_KEY に設定してください。"
                )
            else:
                fallback_msg = f"Gemini API処理エラー: {err_str}"

            return {
                "answer": self._enforce_character_limit(fallback_msg, max_chars),
                "char_count": len(fallback_msg),
                "max_chars": max_chars,
                "document_count": len(pdfs),
                "sources": [pdf["name"] for pdf in pdfs],
                "is_mock": True
            }




    def _enforce_character_limit(self, text: str, max_chars: int) -> str:
        """
        Safely manage text length to match max_chars while ensuring complete sentences.
        """
        text = text.strip()
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        punctuations = ['。', '！', '？', '\n']
        last_punct = -1
        for p in punctuations:
            idx = truncated.rfind(p)
            if idx > last_punct:
                last_punct = idx

        # Only trim at punctuation if it retains at least 80% of target max_chars
        if last_punct >= int(max_chars * 0.75):
            return truncated[:last_punct + 1]
        else:
            # Otherwise append graceful completion mark
            return truncated.rstrip() + "..."


    def _generate_mock_answer(self, question: str, max_chars: int) -> str:
        """Generate cute mock answer when API keys are not provided."""
        sources = [doc["name"] for doc in self.fetch_all_pdfs()]
        mock_text = (
            f"💖【Google Drive横断参照デモ結果】💖\n"
            f"「{question}」についての回答です✨\n"
            f"Drive内の資料（{', '.join(sources)}）を参照しました！\n"
            f"本アプリはサイバー認証を突破したあなた専用のQ&A端末です。"
            f"GEMINI_API_KEYを.envに設定すると、実際のAIによる高度な複数PDF横断解析が行われます♪"
        )
        return self._enforce_character_limit(mock_text, max_chars)
