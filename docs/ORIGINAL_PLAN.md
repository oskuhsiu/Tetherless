# iOS 手機端側載與自動續期工具：開發計劃 v1.0

- 文件日期：2026-10-02（Asia/Taipei）
- 開發模式：個人／單人開發者；優先維持小型、可稽核的開源分支。
- 主要使用者：使用自己的免費 Apple Account／Personal Team 側載 App 的使用者。
- 核心目標：首次設定完成後，日常不接電腦、不啟動管理器、不手動按續期，即可在授權到期前完成手機端續期。
- 次級目標：首次安裝與配對也只用手機完成；此目標與日常自動續期分開驗證。
- 研究狀態：已查核官方文件、專案 README、發佈紀錄及相關 issue／PR；未進行實機、網路封包、二進位或長期背景測試。本文的成功率、可靠性與相容性要求都是待驗收目標，不是已取得的測試結果。

## 1. 決策摘要

推薦以 **SideStore 的小型分支**作為起點，保留已存在的登入、簽署、裝置通訊能力，將開發資源集中在「無介面續期、排程冗餘、到期驗證、自身存活及安全稽核」。不從頭實作 Apple 認證協定，也不先重做桌面 Sideloadly。[S04][S07][S08]

架構原則是 **手機端執行、profile-only refresh 優先、既有本機 VPN helper、使用者授權的捷徑自動化主觸發、iOS 背景工作補充**。雲端服務不持有使用者密碼、簽署私鑰或配對資料；每日續期不依賴開發者的 Mac、常駐電腦或自架簽署伺服器。

普通續期不等於每次重新解壓、重簽與安裝整個 IPA。SideStore 已有只更新 provisioning profiles 的實作歷史；這是本計劃最重要的效能及背景執行基礎。但必須驗證目前選定版本、簽署條件及實機作業系統是否真的接受新 profile，不能由過去 PR 推定所有環境都能成功。[S05][S06]

「只需登入」定義為降低帳號／憑證的人工管理，而不是替使用者跳過系統安全確認。首次仍可能需要 2FA、Developer Mode、配對 PIN、VPN／本機網路授權，以及捷徑自動化確認。正常運作期間不需要每七天重複這些設定。[S02][S03][S11][S14]

## 2. 產品目標與承諾範圍

### 2.1 驗收層級

| 層級 | 目標 | 交付定位 |
|---|---|---|
| A | 手機上匯入、簽署與安裝可信 IPA | 基礎能力，但不是專案完成條件 |
| B | 初次設定後，手機自行在背景續期；不接電腦、不開管理器 | v1.0 核心驗收 |
| C | iOS 27 以上，配對建立／失效後的重新配對可在手機完成 | 降低支援成本的優先改善；仍需 PIN／系統確認 |
| D | 一部沒有管理器、沒有既有配對的手機，也能完成首次安裝 | 獨立研究目標，不以 C 冒充 D |
| E | 關機、長期離線、強制結束、撤銷授權等任意情況仍永久自動續期 | 不作產品承諾 |

v1.0 的主線可接受「首次借助既有工具安裝一次」，但不能接受「每週打開管理器」作為正常流程。通知使用者按續期，只能列為異常恢復，不算自動續期完成。

### 2.2 作業假設

先支援一個 Apple Account、一部裝置、管理器本身及一至兩個一般測試 App。目標測試矩陣包含 iOS 26.x 與 iOS 27.x 的實際選定版本；是否支援某個小版本，必須記錄實機驗證結果，不能把研究能力當成完整相容性承諾。

免費 Personal Team 的官方限制包括最多 10 個 App IDs、3 部登記裝置及每部裝置最多 3 個 App；相關 profile 的期限為核發後七天。管理器自己通常也占一個免費側載 App 名額。正式配額判斷要讀取帳號與系統實際狀態，不以「我們只裝兩個 App」推定仍有額度。[S01]

付費個人開發者模式可以另做，但不能拿較長的 profile 有效期，冒充免費帳號七日自動續期驗收成功。

### 2.3 明確排除

v1.0 不做越獄、永久簽章漏洞、三 App 限制繞過、DRM 解密、tweak 注入、JIT、App 容器、企業憑證轉售、雲端代管使用者 Apple 密碼、商店內容聚合、完整 Windows／Linux 桌面工具或多帳號共用憑證池。

## 3. 已查核的技術依據

| 事實 | 設計含義 | 來源 |
|---|---|---|
| SideStore 是手機端側載工具，使用個人簽署與本機通訊 helper | 重用基礎，比重寫認證與安裝協定更適合單人維護 | [S04] |
| SideStore 的 profile-only refresh 已將一般續期與重裝分離 | 每日工作走小型 profile 更新；完整重簽只作必要路徑 | [S05] |
| 歷史 issue 曾出現系統 profile 更新成功、資料庫日期卻未保存 | 系統狀態、資料庫及 UI 必須分開驗證；該 issue 已關閉，不宣稱目前仍存在 | [S06] |
| SideSign 提供 Swift 簽署、憑證、開發者 API 與認證能力 | 不另寫第二套 Apple 登入堆疊 | [S07] |
| SideStore/minimuxer 現行 README 包含 profile 管理、裝置通訊及 iOS 27 無線配對 | 先評估現行整合介面，不只照舊 Rust minimuxer 教學實作 | [S08] |
| StikPair 說明 iOS 27 以上可在手機建立配對 | 可減少配對對電腦的依賴；不能證明首次安裝問題已解決 | [S11] |
| AnisetteKit 提供手機端 Anisette 路線 | 不把遠端 Anisette 伺服器列為必然依賴；需處理二進位來源與授權 | [S09] |
| Apple 不保證一般 App 固定間隔背景執行 | 採提早續期、冗餘觸發與實測，而不是模擬桌面 cron | [S02] |

### 3.1 版本基線風險

截至查核日，SideStore 最新發佈端點列出 `0.7.0-alpha`，發布於 2026-09-15，說明其修正 Apple 端變動導致舊版登入出現 503 的問題。它的名稱仍為 alpha；不得僅因 GitHub 的 Latest 或 prerelease 欄位就視為已驗證穩定版。[S12]

G0 必須選定可取得、可重建且通過實測的 source commit，固定 submodules、Swift packages、Rust crates 及 binary frameworks。發佈頁列出的版本與 SHA 只作候選線索，不等於本計劃已成功建置該版本。不要預設舊版比較安全，也不要直接追蹤 nightly／develop 作為正式更新來源。

## 4. 使用者流程與首次安裝方案

### 4.1 v1.0 基準流程：首次一次安裝，日常純手機

使用者用既有 iLoader 等工具完成管理器首次安裝與必要配對。此工具只作引導，不需要常駐，也不要求之後每七天使用。開發者不另做自己的桌面 GUI。[S13]

手機初次啟動後，精靈集中處理帳號登入、2FA、帳號／Team 確認、配對與 VPN 可用性，以及一次捷徑自動化設定。使用者不手動管理 CSR、憑證、App ID、UDID 對應或 profile 檔案。

精靈在真正完成一次「鎖屏、無管理器前景介面」測试前，不顯示「自動續期已啟用」。若只完成登入與手動續期，應顯示「安裝可用，自動續期尚未驗證」。

### 4.2 手機端配對與恢復

對 iOS 27 以上，先研究現行 minimuxer 的 wireless pairing 與 idevice 協定能力，將 PIN／授權流程放入精靈，不要求使用者輸出、尋找、分享配對檔。StikPair 可作流程參考，但其非商業條款不適合直接視為一般 MIT 依賴。[S08][S10][S11]

配對失效而管理器仍有效時，引導手機重新配對；這是例外的互動步驟，不是每週操作。管理器已過期時，它不能再執行自己的修復流程，必須另有外部安裝入口。不可將「可重新配對」等同「任何失效皆可自救」。

### 4.3 首次也不用電腦：獨立工作流

| 路線 | 評估與定位 |
|---|---|
| 所有人免費帳號、乾淨手機、瀏覽器登入後直接安裝管理器 | 尚未建立完整可交付的信任／安裝鏈；列為研究，不預先宣稱可用 |
| 個人開發者的有限 Ad Hoc 測試發佈，再接手機端配對 | 可作小規模測試研究；需要已登記裝置、符合發佈條件的簽署材料與手機安裝入口驗證，不是無限量公開通路 |
| App Store 上架任意 IPA 管理器 | 不把審核通過當作既定前提；需評估 2.5.2 等規則 |
| 共用企業憑證、來源不明付費簽名站 | 不採用，避免重新引入更高的憑證、撤銷及帳號風險 |

Apple 的付費 Developer Program 提供 registered-device／Ad Hoc 路線，但每個 membership year、每個產品家族有裝置名額限制。這僅支撐有限裝置測試的候選架構，不能單憑這項規則斷言所有 OTA 手機安裝步驟已驗證。[S16][S17][S18]

研究 Ad Hoc bootstrap 時，必須分清「管理器由開發者 Team 簽署」與「目標 App 由使用者 Team 簽署」。不得將前者的 profile 換成使用者 Team 的 profile 就當作完成身分遷移；Team 改變可能需要完整重簽與資料／Keychain 遷移設計。主線避免這個複雜度，先由使用者 Team 安裝管理器。

本計劃的「免電腦」指使用者操作，不表示開發者不用 Mac／Xcode 建置 iOS App。

## 5. 系統架構

```text
初次精靈 / App Intents / iOS BackgroundTasks
                     │
                     ▼
             RenewalCoordinator
       單一工作鎖、預算、恢復、優先序
                     │
       ┌─────────────┼──────────────┐
       ▼             ▼              ▼
   AccountAgent   ProfileService   RenewalJournal
   本機 Anisette   取得/比對授權     狀態與證據保存
   Apple 認證      不任意換憑證      不儲存秘密
       │             │
       └──────┬──────┘
              ▼
          DeviceGateway
     minimuxer / idevice / 本機通道
              │
       ┌──────┴───────────┐
       ▼                  ▼
 profile-only 更新     必要時完整簽署安裝
       │                  │
       └────────┬─────────┘
                ▼
         系統狀態驗證 → 原子提交
```

### 5.1 技術選型

管理器採原生 Swift，沿用既有 SwiftUI／UIKit 與 Core Data 結構；不為了架構整齊而先全面重寫資料層。SideSign 負責認證與簽署相關能力；minimuxer 作裝置通訊邊界，必要的 Rust／C 能力由現有 FFI 包裝。[S07][S08][S10]

v1.0 使用既有 LocalDevVPN helper，不另造 VPN 產品。免費簽署下可用的 entitlements、helper 分發與單 App 整合不是同一件事；使用現有 helper 能避免把這些問題同時納入第一版。[S04][S15]

本機 VPN 是讓手機能與自身裝置服務通訊的路徑，不代表所有 App 網路活動都離線。Apple 認證與取得新 profile 仍需網路。實作必須量測及核對 helper 的路由，不憑 README 宣稱就直接視為已通過流量稽核。[S15]

### 5.2 輕量化及可維護性

新增程式以協調、驗證、日誌與 UX 為主，減少對上游簽署核心的分叉。先建立 adapter 與回歸測試，再調整底層。避免新增常駐後端、獨立帳號系統、第二個簽署實作及自訂更新協定。

## 6. 登入、憑證與授權管理

### 6.1 認證行為

使用者輸入帳號及完成 2FA 後，由 App 取得必要工作階段，處理 Team、裝置與 App ID。登入資料只透過已審查的認證程式與 Apple 端交握，不經本產品伺服器。

這不是一般「Sign in with Apple」身分登入按鈕就能取代的流程；SideSign 使用的開發者認證與 portal 能力需要獨立審查。[S07]

優先使用可安全保存、可續用的工作階段資料。如果選定認證實作確實需要再次取得密碼才能持續自動登入，必須提供明確的 Keychain 保存同意；不能既完全不留必要憑證，又保證工作階段永遠不失效。密碼不可逆雜湊也不能直接替代需要重新認證的原始秘密。

收到 2FA、安全挑戰或需要同意新條款等情況時，進入 `NEEDS_AUTH`，停止密集重試，保留尚有效的已安裝 App。重新登入屬例外恢復，不作「第一次登入後永久不再詢問」承諾。

### 6.2 憑證策略

憑證、私鑰與 App ID 盡量重用；不能每次續期都重新申請憑證，也不能為解決額度問題，自動撤銷不屬於本工具管理的憑證。先檢查原憑證有效性，再判斷是否需要輪替。遇到未知憑證或配額衝突，清楚解釋，不以撤銷其他工具的憑證作靜默修復。

憑證輪替與一般 profile 續期是兩種工作。輪替可能使既有二進位簽章不再符合新 profile，必須走完整重簽、安裝與恢復流程。

## 7. 續期引擎：快路徑與完整路徑

### 7.1 正常每日工作：profile-only

先確認目前安裝 App 的簽署身分、Team、Bundle ID、必要 extension、UDID 與 entitlements。當程式版本及簽署條件不變時，取得新的授權 profile，經裝置服務更新，不重新下載、解壓與重簽整包 IPA。[S05]

快路徑必須檢查新 profile 是可用的 Apple 授權、與已安裝二進位匹配，且能實際延展原有有效期。若 Apple 回傳未延長的既有 profile，只能記錄「檢查成功、未延展」，不能虛報「續期成功」。

先更新管理器自身的 profile，再處理其他 App。每部裝置的 profile 安裝操作序列化，避免捷徑、手動入口與背景排程同時操作相同裝置服務。

### 7.2 必要時完整重簽／安裝

新增 App、升級二進位、變更 entitlements、簽署憑證輪替，或經測試確認不適用快路徑的情況，才使用完整路徑。重簽與安裝需處理巢狀元件、磁碟空間、原始 IPA 快取、相容性及取消恢復；不能以無限重試完整安裝取代錯誤分類。

大型安裝可能需要使用者前景操作。這不應成為每七天的常態；若選定環境每次到期都必須前景重裝，即未達本計劃核心目標。

### 7.3 管理器自己不能先死掉

日常 profile-only 自身續期不應觸發二進位重裝。只有管理器版本或簽署身分確實需要改變，才走 self-reinstall。

必須 self-reinstall 時，先保存工作 journal，確認安裝材料與恢復入口，安排獨立的自更新交易；不能在程序可能被終止後仍依赖記憶體中的後續工作。若管理器期限緊急，優先完成它的存活工作；不讓大型目標 App 佔滿整次執行預算。

到期後才試圖叫醒管理器救自己，不能作可靠方案。第二個同樣七天到期、又依賴第一個程式維持的 helper，也不算獨立恢復保障。

### 7.4 有效期與驗證

每個必需執行元件選出實際適用的授權 profile，檢查其身分、裝置、entitlements 與簽署憑證，計算目前可用期限。不要把所有歷史 profile 中最早的到期日當作現況，也不要只讀封裝內舊的 embedded.mobileprovision，忽略裝置已更新的 profile。

可用期限模型：

```text
effectiveExpiry = min(
  主 App 的有效授權截止,
  每個必要 extension 的有效授權截止,
  對應簽署憑證的有效截止
)
```

撤銷、簽章錯誤、裝置授權失效是額外的無效條件，不會因上式日期尚未到達而自動變成有效。帳號 session 的期限另外保存，它影響下一次能否續期，不能和 App 目前可執行期限混成一個欄位。

每次成功至少要有「Apple profile 已取得、裝置套用成功、適用 profile 可核對、journal／資料庫持久化成功」的證據。若某個 OS 版本無法取得足夠的系統狀態，記為 `APPLIED_UNVERIFIED`，由實際跨原到期日啟動測試補足，不能聲稱完整驗證成功。

## 8. 不打開 App 的觸發策略

### 8.1 主觸發：使用者授權的捷徑自動化

提供單一 `Refresh Managed Apps` App Intent，其執行不要求切到管理器畫面。初次精靈引導使用者建立每日一次的時間自動化，並選擇可用的立即執行／鎖屏允許設定；可再增加接上充電器時的機會觸發。不同 OS 的選項文字及逐動作授權可能不同，須依目標版本測試。[S03]

不得把捷徑寫成「先開啟管理器，再模擬按續期」。也不能假設 App 可以無聲替使用者建立所有個人自動化。精靈提供流程、範本及自檢，使用者處理不可省略的確認。

App Intent 中直接進入同一續期引擎。若某個初始化、登入、Keychain 存取、VPN 啟動或配對步驟偷偷依賴前景控制器，必須修正或標記能力不符。

### 8.2 輔助觸發：BackgroundTasks

BGAppRefresh／BGProcessing 作補充機會，由系統決定執行時機。所有入口都先查到期狀態、合併重複請求並遵守取消與實際可用預算，不把 earliestBeginDate 當作鬧鐘。[S02][S19]

BGContinuedProcessingTask 適合使用者啟動後需要繼續的工作，不能把它當成無人值守週期排程器。靜默推播、伺服器 cron 或背景 URLSession 也不會單獨替管理器取得任意時刻的本機續期執行權。[S19]

禁止以播放無聲音樂、假定位、假 VoIP 等方式偽裝用途維持存活。

### 8.3 時間與重試政策

以下是第一版待實測的政策，不是 iOS 保證提供的執行頻率：

| 情況 | 處理 |
|---|---|
| 正常，距上次已驗證續期超過 24 小時 | 在下一個有效觸發嘗試續期 |
| 任一管理 App 距有效期不足 72 小時 | 提高優先序；有執行機會就優先處理 |
| 失敗且仍有充足期限 | 分類退避，等待下一個獲准觸發；不假設退避時間一到程序會醒来 |
| 48／24 小時內仍未成功 | 逐級本機通知，提供明確恢復入口 |
| 需要 2FA／PIN／人工授權 | 停止無效重試，標記必要介入 |

正常情況成功後不顯示干擾通知。通知不是續期機制；只是當無法自動恢復時降低使用者毫不知情地到期的風險。

帳號服務、VPN 或網路錯誤都應有重試上限與短路機制。日期持久化採 UTC；排程展示使用使用者時區。時鐘／時區改變不得變成繞過 Apple 授權期限的方法。

## 9. 狀態模型及交易恢復

| 資料類型 | 主要內容 | 安全／一致性規則 |
|---|---|---|
| AccountState | Team、認證狀態、秘密引用 | 資料庫不存密碼、token 原文 |
| DeviceState | OS build、配對狀態、通道能力、配對資料引用 | 配對資料視為高權限秘密 |
| ManagedApp | 原始／重簽 Bundle ID、版本、extension、IPA 雜湊、管理模式 | 維持穩定身分，不靜默改 Team |
| SigningIdentity | 憑證指紋、有效期、私鑰引用 | 不隨意撤銷共享帳號下其他憑證 |
| ProfileLease | profile UUID、適用元件、有效期、驗證狀態 | 區分收到、套用、核對三個階段 |
| RenewalRun | 觸發來源、階段、方式、耗時、結果與遮罩後錯誤 | 失敗重啟可恢復；不包含秘密 |

工作狀態：

```text
QUEUED → PREFLIGHT → AUTH_READY → PROFILE_READY
       → APPLYING → VERIFYING → COMMITTED
```

旁支：`DEFERRED`、`NEEDS_AUTH`、`NEEDS_PAIRING`、`NEEDS_FOREGROUND`、`APPLIED_UNVERIFIED`、`FAILED`。

`COMMITTED` 只能由驗證與持久化完成後產生。系統操作已成功但資料庫提交失敗時，下次應先對帳，不立即再申請一套憑證或刪除現有 profile。[S06]

同裝置只允許一個寫入交易。若 App Intent 與主程序／extension 分開執行，需跨程序互斥，不能以單一 Swift actor 當作跨程序鎖。取得鎖後重新讀取狀態，避免第二個執行者使用過期快照。

## 10. 安全門檻

### 10.1 本機秘密保存

密碼（若有明確同意保存）、工作階段、簽署私鑰及配對秘密保存於 Keychain／受保護儲存，不進一般偏好設定、Documents、共享雲端或診斷報告。

背景需要的秘密可評估 `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`：它支援重新開機後首次解鎖以後的背景存取，不是開機未解鎖即可取用，也不保證抵禦所有已解鎖裝置威脅。需依其安全取捨取得使用者理解，不設定每次背景存取都要求 Face ID，否則會破壞無人值守流程。[S20]

帳號建議使用專用測試帳號。開源只提供審查機會，不能代替實際審查、依賴檢查與發行檔驗證。

### 10.2 Anisette 與通道

優先使用經審查的手機端 Anisette。AnisetteKit 的 ADI 二進位來源、可否分發、更新方式與雜湊都必須記錄；函式庫授權不會自動解決第三方二進位的權利問題。[S09]

不得因本機生成失敗便靜默把秘密送給公共遠端服務。若另提供遠端 Anisette 備援，必須使用者明確開啟，說明會送哪些資料，且仍不得上傳 Apple 密碼、私鑰、配對紀錄或 IPA。初始化狀態快取與每次新鮮驗證值分開管理。

本機 VPN 衝突時，不能無聲關掉使用者的公司／隱私 VPN。回報通道受阻，必要時請求一次互動。路由只給必要通訊，不建立未知外部控制入口。

### 10.3 IPA 與供應鏈

解壓縮拒絕路徑逃逸、越界連結、異常膨脹與資源超額；驗證 entitlement 差異與 nested signing，拒絕不支援的加密或封裝，不為了「成功安裝」靜默移除關鍵能力。匯入內容不可信，簽署流程本身不能執行其程式碼。

固定依賴版本，建立 SBOM，保存來源與 build metadata，檢查 binary XCFramework 的來源。正式版不無聲追 nightly；程式更新與授權續期分開。個人簽章使 App 可執行，不足以證明 IPA 原始發布者身分，仍需校驗可信發行來源與內容雜湊。

### 10.4 網路稽核

在可觀測測試環境盤點所有連線目的與資料類型，核對帳號認證僅走預期 Apple 流程、helper 是否僅有預期路由，以及錯誤回報是否遮罩。TLS pinning 等限制應如實記錄；無法觀察的內容不能填成「已確認不外傳」。

## 11. 分階段開發與交付

階段採驗收門檻，而非未經實測的固定工期。最大不確定性是鎖屏背景路徑和 Apple 端認證變動；先驗證這兩項，再投入完整 UI。

| 階段 | 工作 | 交付物 | 通過條件 |
|---|---|---|---|
| G0 基線與權利盤點 | 建置選定 SideStore、記錄依賴、登入／profile／裝置通訊調用鏈及授權 | baseline-lock、SBOM、資料流、license matrix | 可重建；無未處理的核心分發授權障礙；不知道的地方有明確標記 |
| G1 profile-only 實證 | 管理器＋測試 App 的手機續期、系統 profile 核對、跨原到期日測試 | profile 更新 PoC、前後證據、完整路徑條件 | 不以完整重裝作正常續期；日期與實際可啟動相符 |
| G2 無前景自動化 | App Intent、捷徑、背景入口、Keychain、通道恢復、互斥與預算 | headless renewal、設定精靈、自檢 | 鎖屏時由授權自動化完成；不開管理器；不連電腦 |
| G3 安裝與失敗恢復 | IPA 處理、憑證輪替、journal、self-reinstall、安全錯誤分類 | 最小可用分支、異常恢復手冊 | 正常續期保留資料；必要介入具體可理解；不破壞其他工具憑證 |
| G4 長期與安全驗收 | 30 天真實時間測試、故障注入、資源與連線檢查 | 相容性矩陣、測試報告、已知限制、候選發行版 | 在已聲明條件下零到期中斷、零例行手動續期；安全測試無未處理高風險 |
| G5 純手機引導 | iOS 27 配對整合、有限測試的無電腦首裝路線 | bootstrap PoC、乾淨裝置證據、限制說明 | 沒有預裝管理器／既有配對的裝置可走完整流程；否則仍列未完成 |

G1／G2 失敗時，不以漂亮 UI、通知或「點一下就好」宣稱完成。先修正能力落差，或縮小正式支援的版本／條件；若仍不能達標，保留研究分支，不發布符合本目標的 v1.0。

### 11.1 可直接拆票的優先工作

| ID | 任務 | 依賴 | 完成證據 |
|---|---|---|---|
| BASE-01 | 固定來源與可建置依賴 | 無 | 完整 SHA／lock 檔與重建紀錄 |
| BASE-02 | 核對授權與第三方二進位 | BASE-01 | 逐項可用／需許可／待釐清清單 |
| AUTH-01 | 登入與秘密儲存審查 | BASE-01 | 憑證流向圖、遮罩測試 |
| LEASE-01 | 分離 profile-only 與完整安裝 | BASE-01 | 兩條路徑的條件測試 |
| LEASE-02 | 系統 profile 對帳與有效期 | LEASE-01 | 不靠 UI 倒數的前後證據 |
| AUTO-01 | App Intent 無前景入口 | AUTH-01、LEASE-02 | 鎖屏執行記錄 |
| AUTO-02 | 捷徑精靈與真實自檢 | AUTO-01 | 初次授權後無需 Open App 動作 |
| AUTO-03 | 冗餘排程、互斥、取消與退避 | AUTO-01 | 競態／取消／重入測試 |
| SAFE-01 | 管理器自身 profile 續期 | LEASE-02 | 跨原七日到期仍可繼續自動執行 |
| SAFE-02 | 提交失敗對帳與重啟恢復 | AUTO-03 | 不重複建立資源、不假成功 |
| INSTALL-01 | 可信 IPA 的完整重簽安裝 | AUTH-01 | 身分及資料保留測試 |
| INSTALL-02 | 憑證輪替與自身重裝 | SAFE-01、SAFE-02、INSTALL-01 | 程序被中止後可恢復的證據 |
| PAIR-01 | iOS 27 手機端配對 | BASE-02、AUTO-01 | 無配對檔手動搬運 |
| QA-01 | 無前景 30 日觀察 | AUTO-02、AUTO-03、SAFE-01 | 不混入手動刷新／debugger 的完整紀錄 |
| QA-02 | 安全與資源檢查 | AUTH-01、INSTALL-01 | 秘密不外洩、輸入防護、耗電與耗時基線 |
| BOOT-01 | 乾淨手機首次安裝研究 | PAIR-01、BASE-02 | 完整安裝鏈，含未解決的限制 |

## 12. 測試計劃

### 12.1 兩組實機，避免自我欺騙

**背景觀察組**：首次設定後連續 30 天不開管理器、不手動呼叫續期、不接桌面、不接 debugger；只使用事先授權的自動化與正常手機使用。不能為了讀狀態每天打開管理器，因為那會改變所測的條件。

**正確性／故障組**：刻意檢查 profile、更換網路、跨原到期日啟動 App、注入錯誤、觀察程序被取消後的恢復。這組可使用測試工具，但結果不混充背景觀察組的成功率。

測試使用真實時間。修改系統日期、手動觸發或 Xcode 模擬背景只作單元／整合測試，不替代多週觀察。30 天通過只代表該組條件通過，不等於一般用戶達到 99.9% 可靠性。

### 12.2 環境矩陣

| 場景 | 預期與驗證 |
|---|---|
| 一般 Wi-Fi、鎖屏、管理器不開啟 | 主驗收，自動 profile 續期 |
| 行動網路、無 Wi-Fi | 驗證選定通道／版本；不可僅因新版聲稱支援便標成通過 |
| 48／72 小時離線後恢復 | 仍有有效期時，在下一次機會恢復；記錄預警與期限 |
| 離線直到實際授權全部過期 | 明確列恢復情境，不承諾離線取得新 Apple 授權 |
| 重開機後尚未首次解鎖 | Keychain 不可用時保留狀態；首次解鎖後重新評估 |
| 低耗電模式、未充電或背景機會減少 | 觀察多日續期餘量，不能只測理想充電狀態 |
| 使用者強制結束管理器 | 不宣稱一般背景機制必然重新啟動；記錄實際捷徑行為與必要介入 |
| 公司／其他 VPN 占用 | 不靜默關閉既有 VPN；明確診斷與恢復 |
| 配對失效 | 管理器尚有效時，手機端／引導式重新配對 |
| Apple 2FA、session 過期、503 | 需要認證或暫時故障分開，不無限重試 |
| profile 安裝成功、DB 寫入失敗 | 下次對帳，不讓 UI 舊日期觸發破壞性修復 |
| 憑證撤銷、配額滿、Team 改變 | 不刪除未知憑證，不誤用快路徑 |
| 多入口同時續期 | 單裝置序列化；無重複資源及錯誤覆寫 |
| 低空間、大 IPA、惡意 ZIP | 可恢復失敗，無路徑逃逸或秘密外洩 |
| 目標 App 含 extension | 驗證全部必要 profile 及配額，不只主 App |

### 12.3 指標及發行門檻

記錄每部裝置的到期中斷次數、人工介入次數、背景觸發來源、成功續期距到期的餘量、profile-only／完整安裝比例、p50／p95 耗時、記憶體峰值、網路流量與耗電相對基線。

主驗收條件是，在已聲明的支援環境中連續 30 天無到期造成的不可啟動、無例行前景續期、無電腦依賴。故障組中已設計為需互動的情況分開報告，不從分母中悄悄移除失敗。

無法取得足夠長期資料時，發佈標記為實驗版本，不使用「永久有效」「完全無感」「保證不中斷」等說法。

## 13. 維運、成本與替代架構

單人開發的主要成本是實機、Apple 認證變動、作業系統相容性及依賴授權，不是畫面數量。正常續期採本機計算與直連 Apple，不需要租用持有所有使用者秘密的後端；可用靜態方式發布原始碼、更新資訊及文件。

每次 Apple／iOS 或上游認證更新，先跑最小回歸與金絲雀裝置，再更新支援矩陣。程式版本升級與授權續期是不同管線，不能因每天需要續期就讓每台手機每天裝最新 nightly。[S12]

雲端只幫忙簽署，不等於 profile 已裝進手機。要由遠端完全接手，還需要持續可用的裝置通道、配對權限及本機 helper；這是另一套有高權限秘密暴露面與維運成本的架構，需另外實證，不能當作本計劃背景限制的簡單修補。不納入 v1.0。

付費個人開發者模式可降低 profile 輪替頻率，但它應是一個清楚命名的可選模式，免費七日帳號仍需獨立通過主驗收。

## 14. 授權與分發決策

採 SideStore 分支，預設接受相應開源義務，保留著作權及必要聲明；不打算先做閉源產品，再設法補救依賴問題。標準 GPL／AGPL、修改過的 MIT、非商業條件及商標限制必須分開記錄。以下只是依公開 repo 標示整理，正式整合前需核對選定 commit 的完整 LICENSE 與分發材料。

個人開發者不等於非商業使用。收費、贊助對價、付費服務或重新上架時，不能直接套用「我只有一個人」來忽略 NC 或重製／品牌限制。[S11][S15]

App Store 對下載／安裝其他程式的限制及 VPN 相關要求，使其不是可以無條件依賴的分發通路。保持既有 helper 路線，不將自己提交 VPN App 的審核結果視為已確定；地方替代分發也不能未經資格核對就當作全球免費側載方案。[S18]

## 附錄 A：可參考的 repositories

以下是技術與流程參考，不是已完成安全稽核的下載推薦。所有主分支資訊均需在 G0 固定為實際版本。

| Repo | 用途 | 公開授權／注意事項 | 採用方式 |
|---|---|---|---|
| [SideStore/SideStore](https://github.com/SideStore/SideStore) | 手機側載、App 管理、續期流程基底 | AGPL-3.0；注意發行與分支狀態 | 首選小型 fork／上游貢獻 |
| [SideStore/SideSign](https://github.com/SideStore/SideSign) | Swift 認證、開發者 portal、憑證、IPA 簽署 | GPL-3.0；不等於已完成安全審查 | 優先沿用上游相容版本 |
| [SideStore/minimuxer](https://github.com/SideStore/minimuxer) | 裝置通訊、profile 管理、安裝、無線配對 | AGPL-3.0；現行結構包含 Swift 套件與多 backend | DeviceGateway 的主要邊界 |
| [jkcoxson/idevice](https://github.com/jkcoxson/idevice) | Rust 裝置協定及 FFI | MIT；API／OS 相容性需固定與測試 | 底層能力，不重新發明協定 |
| [mahee96/AnisetteKit](https://github.com/mahee96/AnisetteKit) | 手機端 Anisette | README 標示 AGPL，並有額外分發聲明；須核對 LICENSE 及 ADI 二進位權利 | 通過權利與供應鏈檢查後整合 |
| [jkcoxson/LocalDevVPN](https://github.com/jkcoxson/LocalDevVPN) | 本機 VPN／loopback helper | 自訂 StosVPN License，有署名及重製／品牌條件，不是純 MIT | 優先用既有發布版本，不直接換皮上架 |
| [StikDebug/StikPair](https://github.com/StikDebug/StikPair) | iOS 27 手機配對與 PIN UX | 標示 MIT 加 non-commercial，不能當作標準 MIT | 參考流程；核心優先用 minimuxer／idevice 或先取得許可 |
| [nab138/iloader](https://github.com/nab138/iloader) | 初次安裝、配對引導 | 程式碼 MIT；名稱／品牌資產另核對 | v1.0 使用既有工具，避免自建桌面端 |
| [NRG-Wardog/sidestore-auto-refresh](https://github.com/NRG-Wardog/sidestore-auto-refresh) | 無介面續期、背景調度與實測方法參考 | 實驗性；外層授權不覆蓋上游 copyleft，能力聲明要對照實測狀態 | 只作研究與測試清單參考，不直接當成已證實穩定底座 |

## 附錄 B：官方文件與查核來源

查核日期均為 2026-10-02。本文未引用公眾論壇的「無毒」背書，也沒有把 issue 回報推廣為所有當前版本的事實。

- **[S01] Apple — Developer account overview**：Personal Team 配額與七日期限。https://developer.apple.com/help/account/basics/about-your-developer-account/
- **[S02] Apple DTS — iOS Background Execution Limits**：無固定週期保證、系統調度與 force quit。https://developer.apple.com/forums/thread/685525
- **[S03] Apple — Add automations to Shortcuts**：個人自動化、鎖屏及動作授權。https://support.apple.com/guide/shortcuts/add-automations-apdfbdbd7123/ios
- **[S04] SideStore README**：手機側載架構與 helper。https://github.com/SideStore/SideStore
- **[S05] SideStore PR #846**：一般 refresh 僅更新 profile，與重裝分離；不引用回覆中的速度作本產品承諾。https://github.com/SideStore/SideStore/pull/846
- **[S06] SideStore issue #1405**：2026-08-03 報告、查核時已關閉；profile 更新和資料庫持久化不同步的回歸測試案例。https://github.com/SideStore/SideStore/issues/1405
- **[S07] SideSign README**：認證、簽署與開發者能力。https://github.com/SideStore/SideSign
- **[S08] SideStore/minimuxer README**：通訊、profile 與 iOS 27 無線配對 API。https://github.com/SideStore/minimuxer/blob/develop/README.md
- **[S09] AnisetteKit README／LICENSE**：本機 Anisette 及分發聲明。https://github.com/mahee96/AnisetteKit
- **[S10] idevice README**：底層裝置協定與授權。https://github.com/jkcoxson/idevice
- **[S11] StikPair README／LICENSE**：iOS 27 配對與非商業限制。https://github.com/StikDebug/StikPair
- **[S12] SideStore 0.7.0-alpha 發布**：2026-09-15 發布，修正 Apple 端變動引起的登入問題。https://github.com/SideStore/SideStore/releases/tag/0.7.0-alpha
- **[S13] iLoader README**：首次安裝工具。https://github.com/nab138/iloader
- **[S14] SideStore installation guide**：信任、Developer Mode、首次設定。https://docs.sidestore.io/docs/installation/install
- **[S15] LocalDevVPN README／LICENSE**：本機通道與自訂條款。https://github.com/jkcoxson/LocalDevVPN 及 https://github.com/jkcoxson/LocalDevVPN/blob/main/LICENSE
- **[S16] Apple — Devices overview**：付費會員 registered-device／Ad Hoc 裝置配額。https://developer.apple.com/help/account/devices/devices-overview/
- **[S17] Apple — Create an ad hoc provisioning profile**：Ad Hoc profile 的簽署與已登記裝置條件。https://developer.apple.com/help/account/provisioning-profiles/create-an-ad-hoc-provisioning-profile/
- **[S18] Apple — App Review Guidelines**：尤其 2.5.2、2.5.4 與 VPN 相關條文。https://developer.apple.com/app-store/review/guidelines/
- **[S19] Apple WWDC25 — Finish tasks in the background**：BackgroundTasks 類型與 user-initiated continued processing 的定位。https://developer.apple.com/videos/play/wwdc2025/227/
- **[S20] Apple — kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly**：背景秘密存取的條件。https://developer.apple.com/documentation/security/ksecattraccessibleafterfirstunlockthisdeviceonly
- **[S21] SideStore auto-refresh research**：實驗性背景續期設計，不能代替本計劃實測。https://github.com/NRG-Wardog/sidestore-auto-refresh

## 附錄 C：交給實作 agent 的起始任務

先完成 BASE-01、BASE-02、AUTH-01 與 LEASE-01，不做大規模重構與 UI 換皮。閱讀選定版本的實際登入、取得 profile、安裝 profile、保存到期日及 App Intent 調用鏈，列出前景依賴和秘密儲存位置；所有路徑以 repo 當前內容為準，不依文件中的類別名猜測實際檔案位置。

第一個實證成果必須是：在一部已完成初次安裝的真實 iPhone 上，由一次已授權的自動化，在鎖屏且沒有打開管理器的情況下，更新管理器自己和一個測試 App 的授權 profile，保存可核對的證據。首次成功只是 G1／G2 的材料，不代表 30 天可靠性已完成。

後續依本計劃分離正常續期、完整重簽與例外恢復，保留最小變更，優先補回歸測試。無法通過的 gate 與原因必須寫入報告；不得把提醒通知、Open App 捷徑、手動按鈕或更換付費帳號，計為免費帳號無前景自動續期的完成證據。
