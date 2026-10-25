let accessToken = ''
export const setAccessToken = token => { accessToken = token || '' }

const request = async (url, options = {}) => {
  const headers = { ...options.headers }
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  const response = await fetch(`/api/v1${url}`, { ...options, headers })
  if (!response.ok) {
    if (response.status === 401 && accessToken) {
      setAccessToken('')
      window.dispatchEvent(new Event('session-expired'))
    }
    let message = `请求失败：${response.status}`
    try {
      const body = await response.json()
      message = Array.isArray(body.detail) ? body.detail.map(item => `${item.loc?.slice(-1).join('') || ''}：${item.msg}`).join('；') : body.detail || message
    } catch { /* Preserve HTTP status for non-JSON responses. */ }
    throw new Error(message)
  }
  return response
}
const get = async url => (await request(url)).json()
const post = async (url, body) => (await request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json()
export const loginSession = body => post('/auth/login', body)
export const logoutSession = () => post('/auth/logout', {})
export const getMetadata = () => get('/metadata')
export const getDashboard = scenario => get(`/dashboard?scenario=${encodeURIComponent(scenario)}`)
export const getAnalysis = (id, scenario) => get(`/companies/${encodeURIComponent(id)}/analysis?scenario=${encodeURIComponent(scenario)}`)
export const getDataStatus = () => get('/enterprise/data-status')
export const syncEnterpriseData = body => post('/enterprise/data-sync', body)
export const getReviewTasks = () => get('/review-tasks')
export const getReviewTask = id => get(`/review-tasks/${encodeURIComponent(id)}`)
export const submitEvidence = async form => (await request('/enterprise/evidence', { method: 'POST', body: form })).json()
export const reviewDecision = (id, body) => post(`/review-tasks/${encodeURIComponent(id)}/decision`, body)
export const getMaterial = async id => (await request(`/materials/${encodeURIComponent(id)}`)).blob()
