"""
整個專案的發布版本（只在這裡改一次）。每次發版：① 改 RELEASE ② 把這版有改動的檔案與其版本寫進 EXPECT ③ 更新 CHANGELOG 與 updates.py。
試跑與正式發布會拿 EXPECT 跟各檔案實際的版本號比對，不一致就在摘要最上面警告（代表有檔案忘了上傳或傳到舊版）。
"""
__version__ = "1.10.3"
RELEASE = "1.10.3"
EXPECT = {"version": "1.10.3", "topics": "1.10.1", "pipeline": "1.10.3", "episode": "1.10.3", "main": "1.10.3",
          "prices": "1.10.3", "watchlist": "1.10.0", "updates": "1.10.3", "fetcher": "1.9.1", "numcheck": "1.7.1",
          "tts": "1.10.3", "guard": "1.10.3"}
