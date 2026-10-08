const json = async (url) => {
  const response = await fetch(url)
  if (!response.ok) throw new Error((await response.json()).detail || `请求失败：${response.status}`)
  return response.json()
}

export const getMetadata = () => json('/api/v1/metadata')
export const getDashboard = scenario => json(`/api/v1/dashboard?scenario=${encodeURIComponent(scenario)}`)
export const getAnalysis = (companyId, scenario) => json(`/api/v1/companies/${companyId}/analysis?scenario=${encodeURIComponent(scenario)}`)
