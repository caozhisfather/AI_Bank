// Matches the existing monitoring rule in services/analysis_service.py.
export const LOW_TARGET_PROBABILITY = 0.7

export const isLowTargetProbability = value => Number.isFinite(value) && value < LOW_TARGET_PROBABILITY

export const isProductionLed = attribution => attribution?.reduction_profile?.kind === 'production_led'
  || attribution?.assessment_summary === '产量收缩主导'
