// 学习台剪藏 · Background Service Worker
// 右键菜单：剪藏选中文字/当前页面到学习台待办

const API_BASE = 'https://your-domain.com:8443/api/v1'

// 读取存储的配置
async function getConfig() {
  const data = await chrome.storage.sync.get({ apiBase: API_BASE, token: '' })
  return data
}

// 发送到后端
async function sendToTodo(title, content, url) {
  const cfg = await getConfig()
  if (!cfg.token) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: '学习台剪藏',
      message: '请先在扩展设置中配置 API Token',
    })
    return false
  }
  try {
    const resp = await fetch(`${cfg.apiBase}/todos/from-extension`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Token': cfg.token,
      },
      body: JSON.stringify({ title, description: content, url }),
    })
    if (resp.ok) {
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: '学习台剪藏',
        message: `已剪藏：${title.slice(0, 30)}`,
      })
      return true
    }
    const err = await resp.json().catch(() => ({}))
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: '剪藏失败',
      message: err.detail || `HTTP ${resp.status}`,
    })
    return false
  } catch (e) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: '剪藏失败',
      message: e.message || '网络错误',
    })
    return false
  }
}

// 创建右键菜单
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'clip-selection',
    title: '剪藏选中文字到学习台',
    contexts: ['selection'],
  })
  chrome.contextMenus.create({
    id: 'clip-page',
    title: '剪藏当前页面到学习台',
    contexts: ['page'],
  })
})

// 右键菜单点击
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = tab?.url || ''
  const pageTitle = tab?.title || ''
  if (info.menuItemId === 'clip-selection' && info.selectionText) {
    await sendToTodo(
      info.selectionText.slice(0, 50),
      info.selectionText,
      url,
    )
  } else if (info.menuItemId === 'clip-page') {
    await sendToTodo(
      pageTitle,
      `${pageTitle}\n${url}`,
      url,
    )
  }
})

// 来自 popup 的消息
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'clip') {
    sendToTodo(msg.title, msg.content, msg.url).then((ok) => sendResponse({ ok }))
    return true
  }
})
