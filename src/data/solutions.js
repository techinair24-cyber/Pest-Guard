// Backend solution records are the source of truth. No recommendation is fabricated in the frontend.
export const solutionFields = ['pest_id', 'pest_name', 'risk', 'affected_crop', 'symptoms', 'recommended_action', 'prevention']

export function normalizeSolution(record) {
  return {
    ...record,
    pest_id: record.pest_id || record.pestId,
    pest_name: record.pest_name || record.pest,
    affected_crop: record.affected_crop || record.crop,
    recommended_action: record.recommended_action || record.action,
  }
}
