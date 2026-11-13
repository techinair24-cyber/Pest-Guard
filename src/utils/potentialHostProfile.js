const PROFILE_SECTIONS = [
  ['Description', 'description'],
  ['Identification signs', 'identification_signs'],
  ['Crop damage', 'crop_damage'],
  ['Affected plant parts', 'affected_plant_parts'],
  ['Recommended treatment', 'recommended_treatment'],
  ['Immediate control measures', 'immediate_control_measures'],
  ['Biological control options', 'biological_control_options'],
  ['Cultural control methods', 'cultural_control_methods'],
  ['Mechanical control methods', 'mechanical_control_methods'],
  ['Chemical control options', 'chemical_control_options'],
  ['Prevention', 'prevention'],
  ['Monitoring', 'monitoring'],
  ['Safety precautions', 'safety_precautions'],
  ['Expert advice', 'expert_advice'],
]

export function buildPotentialHostDisplay(profile) {
  if (
    !profile ||
    profile.status !== 'NEEDS_REVIEW' ||
    !Array.isArray(profile.potential_host_crops) ||
    profile.potential_host_crops.length === 0
  ) {
    return null
  }

  return {
    pestName: profile.pest_name,
    scientificName: profile.scientific_name,
    riskLevel: profile.risk_level,
    region: profile.region,
    verificationLabel: 'Candidate profile',
    hostHeading: 'Potential hosts',
    hosts: profile.potential_host_crops.map((host) => ({
      cropId: host.crop_id,
      cropName: host.crop_name,
      reviewStatus: host.review_status,
    })),
    sections: PROFILE_SECTIONS
      .map(([title, key]) => ({ title, content: profile[key] }))
      .filter((section) => section.content),
  }
}
