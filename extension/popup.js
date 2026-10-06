// popup 脚本：设置 + 快速剪藏
const apiBaseInput = document.getElementById('apiBase')
const tokenInput = document.getElementById('token')
const saveBtn = document.getElementById('saveBtn')
const msgDiv = document.getElementById('msg')

// 加载已保存配置
chrome.storage.sync.get({ apiBase: 'https://your-domain.com:8443/api/v1', token: '' }, (data) => {
  apiBaseInput.value = data.apiBase
  tokenInput.value = data.token
})

saveBtn.addEventListener('click', () => {
  chrome.storage.sync.set({
    apiBase: apiBaseInput.value.trim(),
    token: tokenInput.value.trim(),
  }, () => {
    msgDiv.className = 'ok'
    msgDiv.textContent = '设置已保存 ✓'
    setTimeout(() => (msgDiv.textContent = ''), 2000)
  })
})
