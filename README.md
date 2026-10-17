<p align="center">
  <a target="_blank" rel="noopener noreferrer" href="assets/icon.png">
    <img src="assets/icon.png" alt="Koeiro Icon" width="160" style="max-width: 100%;">
  </a>
</p>

<h1 align="center">Koeiro（声彩）</h1>

<p align="center">
  <strong>登録した声へリアルタイムに変換する次世代ローカルAIボイスチェンジャー</strong><br>
  Windows 10/11 & Linux 対応 ｜ MeanVC2 + LavaSR 帯域復元 ｜ Discord RPC 連携 ｜ 低スペック・CPU環境対応
</p>

<p align="center">
  <a href="https://negix.booth.pm/items/8981333"><img src="https://img.shields.io/badge/BOOTH-配布ページ-EC407A?logo=booth&logoColor=white" alt="BOOTH"></a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-0078D6" alt="Platform">
  <img src="https://img.shields.io/badge/PyTorch-CPU%20%2F%20CUDA%2012-EE4C2C?logo=pytorch&logoColor=white" alt="PyTorch">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

---

## 📖 概要

**Koeiro（声彩 / こえいろ）** は、マイクから入力された音声をリアルタイムで目的の声へと変換するローカル動作型AIボイスチェンジャーです。

超軽量な音声変換モデル **MeanVC2** に加え、高品質な超解像・帯域復元技術 **LavaSR** を統合。配信（OBS）、通話（Discord / Zoom）、VRChat などのVRメタバースに向けて、低遅延かつクリアなボイス変換を提供します。音声データは外部サーバーへ送信されず、すべてお使いのPCローカル環境で完結します。

GUIとAI推論ワーカーを独立したプロセスとして分離するアーキテクチャを採用しており、GUI側の軽快なレスポンスとAI推論の安定動作を両立。GPU非搭載のミニPC（Intel N100 / N150等）やCPU環境でも実用的に動作するよう、CPU 経路を実測して最適化しています。

---

## 🚀 インストール & クイックスタート

### 🌟 【一番おすすめ】BOOTH版（ワンクリック簡単導入）

Pythonのインストールやコマンド操作なしですぐに使いたい方は、**BOOTH版のインストーラー**の利用を推奨します。

👉 **[BOOTH 配布ページはこちら（negix.booth.pm/items/8981333）](https://negix.booth.pm/items/8981333)**

- **Windows**: ダウンロードした `setup.exe` を実行し、画面の指示に従うだけで導入完了（標準では `%LOCALAPPDATA%\Programs\Koeiro` にインストールされます）。
- **Linux**: 配布アーカイブを展開後、同梱のスクリプトを実行して起動します。
- 初めてAIボイスチェンジャーを触る方や、手軽に配信・通話で使いたい方に最適です。

---

### 📦 GitHub Releases 版（手動セットアップ）

#### Windows の場合
1. [Releases](https://github.com/heynegix/koeiro/releases) から `koeiro-vX.Y.Z-windows.zip` をダウンロードし、任意のフォルダ（※全角やスペースを含まない英数字パス推奨）に展開。
2. PowerShell を開き、展開先ディレクトリで初回セットアップを実行：
   ```powershell
   py -3.12 tools/setup_release.py

3.  セットアップ完了後、アプリを起動：
    .\.venv\Scripts\python app.py

Linux の場合

1.  Releases から koeiro-vX.Y.Z-linux.tar.gz をダウンロードして展開。
2.  ターミナルで依存パッケージの導入と初回セットアップを実行：
    # PySide6 の実行ライブラリ（libgl1 等）も含めてインストール
    sudo apt install -y libportaudio2 portaudio19-dev ffmpeg \
        libgl1 libegl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 fontconfig
    python3.12 tools/setup_release.py
3.  セットアップ完了後、アプリを起動：
    .venv/bin/python app.py

[!TIP] アプリ起動後は「調整」引き出しの 「① 配線」 で 入力デバイス（マイク） と 出力デバイス（VB-CABLE やヘッドホン等）
を指定してください。Discord や OBS 側では、Koeiro の出力先と同じ仮想オーディオデバイスを入力として選択します。

✨ 主な機能

  - 用途に合わせた変換モード
      - 逐次変換（Streaming）: 発話しながらリアルタイム・低遅延に変換。通話やゲームプレイに最適。
      - 一括変換（LavaSR 高音質）: 無音区間（約0.8秒）で自動分割し、文全体を一括変換後に LavaSR
        で高域を復元。極めて自然で明瞭な音質を実現。
      - 一括変換 - 最速: 判定待ち時間を約0.6秒まで短縮し、レスポンスを最優先したバッチ変換。
      - Original / Female DSP: AIを介さない素通し（スルー）モード、および軽量DSPによるピッチ・フォルマント加工。
  - 声の登録 & 切り替え
      - 標準で参照ボイスを同梱。目的の声の音声クリップ（wav/mp3等）を追加することで、お好みのキャラクターボイスへの変換が可能（※自作ボイスモデルの追加生成には開発環境が必要です）。
  - Discord Rich Presence（RPC）連携
      - Discord のステータスに「Koeiro で変換中」「使用中のボイス名」をリアルタイム表示。
  - CPU 実測最適化 & GPU（CUDA）自動切替
      - GPU 非搭載のミニPC（Intel N100 / N150 等）でも動く CPU 経路を既定に設計。
      - NVIDIA GPU が検出された場合は CUDA を自動選択（CPU固定も可能）。TF32 を制御して推論の再現性を確保。
  - 洗練されたUI設計（ステージ1枚＋引き出し）
      - メイン画面は入力レベル・遅延・ステータス表示に集中。詳細設定は「調整」「実験」の引き出しに収納。
      - 初回起動時のスポットライトガイドや、GitHub Releases と連携したアプリ内ワンクリック自動アップデートに対応。
  - 話し方の演出・オーディオ処理
      - 感情・抑揚プリセット: Calm / Gentle / Energetic / Sad / Anime Light / Anime
        Expressive / Feminine 等を搭載。
      - 入力の整え（音量の自動均一化）: 小声をAIが認識しやすい音量へ自動リフト（無音区間は増幅しません）。
      - 出力の仕上げ & ノイズ除去: つなぎ目のアーティファクトや耳に刺さる息音を穏やかに抑制。
      - AI出力フォルマント: ピッチを維持したまま声の共振を高域へ寄せ、明るい声色に補正。
  - 配信・通話を加速するショートカット
      - シーン機能: マイク、ボイス、配線、エフェクトをプロファイルとして保存・瞬時呼出。
      - ホットキー: Ctrl+1/2/3 でモード変更、Ctrl+D で Original ↔ 直前変換をトグル。
      - 音声コマンド（β）: ウェイクワード「コエイロ」＋「止めて」「次の声」などのローカル音声操作。
  - 拡張パック（DLC）& 実験機能
      - レイテンシ・ガバナ、囁き検出モード、LAN内GPUを活用する分散推論、話者自動振り分け、Kokoro-82M
        による音声合成（TTS）などを搭載。

🛠️ 動作要件

| 項目             | 要件                                                                                                                              |
| :------------- | :------------------------------------------------------------------------------------------------------------------------------ |
| **OS**         | Windows 10 / 11 (64bit), Linux (Debian 12 / Ubuntu 22.04+ 推奨)                                                                   |
| **Python**     | 3.12 系（ソース実行・Releases版手動セットアップ時）                                                                                                |
| **CPU**        | 4スレッド以上のマルチコアCPU（Intel N100 / N150 等でリアルタイム動作確認済み）                                                                              |
| **GPU**        | 不要（CPUのみで動作可能）。NVIDIA GPU（CUDA 12）搭載環境ではさらに高速動作                                                                                 |
| **メモリ**        | 4GB 以上（AI推論ワーカープロセス実測: 約0.9GB）                                                                                                  |
| **ストレージ**      | 8GB 以上の空き容量（モデル・仮想環境含む）                                                                                                         |
| **外部ツール**      | **FFmpeg**（音声処理用）、**仮想オーディオデバイス**（VB-CABLE、VoiceMeeter 等）                                                                       |
| **Linux 追加依存** | `libportaudio2`, `portaudio19-dev`, `ffmpeg`, `libgl1`, `libegl1`, `libglib2.0-0`, `libxkbcommon0`, `libdbus-1-3`, `fontconfig` |

🎙️ 仮想オーディオデバイスとの接続例（Discord / OBS）

通話アプリや配信ソフトに変換後の声を出力するには、仮想オーディオドライバ（VB-CABLE 等）を利用します。

[物理マイク] ──> 【Koeiro 入力】 ──(AI変換)──> 【Koeiro 出力（CABLE Input）】
                                                        │
                                                        ▼
                                       【Discord / OBS 入力（CABLE Output）】

1.  Koeiro 側の設定:
      - 入力デバイス：お使いのヘッドセット・マイク
      - 出力デバイス：CABLE Input (VB-Audio Virtual Cable)
2.  通話・配信ソフト側の設定:
      - Discord / OBS などの音声入力デバイスに CABLE Output (VB-Audio Virtual Cable) を指定。
      - ご自身の声を確認（モニター）したい場合は、Koeiro の「モニター出力」機能でお使いのヘッドホン・スピーカーを選択してください。

🧪 ソースコードからの実行・開発

リポジトリをクローンして開発環境を構築する場合の手順です。

# 1. リポジトリのクローン
git clone https://github.com/heynegix/koeiro.git
cd koeiro

# 2. 仮想環境の作成と依存関係の導入 (Python 3.12)
python -m venv .venv

# Windows の場合
.\.venv\Scripts\activate
# Linux の場合
source .venv/bin/activate

# 3. 依存ライブラリのインストール
pip install -r requirements.txt
pip install -r requirements-ai.txt

# 4. アプリケーションの起動
python app.py

❓ トラブルシューティング

  - CPUの性能に応じて変換モードを切り替えてみてください。低スペック環境では「一括変換 - 最速」が最も安定します。
  - 「調整」引き出しのバッファサイズ設定（フレーム数）を見直すか、バックグラウンドで動作している高負荷なプロセスを終了してください。

  - 「調整」引き出しの「配線」タブで、入力デバイスと出力デバイスが正しく割り当てられているか確認してください。
  - Windowsのサウンド設定で、マイクおよび仮想オーディオデバイスのサンプリングレートが 48000 Hz (48 kHz)
    に設定されているか確認してください。

  - PySide6（Qt）に必要な共有ライブラリが不足している可能性があります。以下のパッケージが導入されているか確認してください：
    sudo apt install -y libgl1 libegl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 fontconfig

  - BOOTH配布のバイナリ単体にはモデル抽出スクリプトは含まれていません。自作ボイスの追加・特徴抽出を行う場合は、Python 3.12 /
    PyTorch 環境が整った開発環境（tools/ 配下のスクリプト）をご利用ください。

📜 ライセンス & クレジット

  - Koeiro 本体: MIT License (c) 2026 Negix
  - MeanVC2: Apache-2.0 License (ASLP-lab)
  - LavaSR: Apache-2.0 License
  - GUI Framework: PySide6 (LGPLv3)
  - 詳細なサードパーティ製ライブラリおよび事前学習済みモデルのライセンスについては、THIRD_PARTY_NOTICES.md をご参照ください。

[!WARNING]
第三者の音声を本人の許諾なく模倣・再現する行為、なりすまし、公序良俗に反する用途での使用は固く禁止します。倫理的な配慮のもとでご活用ください。
