// Backend pest records are the source of truth. This module documents and normalizes the API shape.
export const pestFields = ['id', 'name', 'scientific_name', 'affected_crop', 'description', 'symptoms', 'risk', 'image']

export function normalizePest(record) {
  return {
    ...record,
    scientific_name: record.scientific_name || record.scientificName || '',
    affected_crop: record.affected_crop || record.crop || '',
  }
}
