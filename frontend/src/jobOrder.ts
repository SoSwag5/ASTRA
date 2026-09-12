type Job = Record<string, any>;
export function isUae(location: string) {
  return /\b(?:U\.?A\.?E\.?|United Arab Emirates|Abu Dhabi|Dubai|Sharjah|Ajman|Fujairah|Ras Al Khaimah|Umm Al Quwain|Al Ain)\b/i.test(location || '');
}
export function compareJobs(a: Job, b: Job, sort: string, primary: string[] = []) {
  const score = Number(b.match_score || 0) - Number(a.match_score || 0);
  const time = (j: Job) => Date.parse(j.date_found || j.created_at || '') || 0;
  const recent = time(b) - time(a);
  const stable = Number(b.id || 0) - Number(a.id || 0);
  const tier = (j: Job) => primary.some(p => p.trim() && (j.location||'').toLowerCase().includes(p.toLowerCase())) ? 1 : 0;
  if (sort === 'uae_first') return Number(isUae(b.location)) - Number(isUae(a.location)) || tier(b)-tier(a) || score || recent || stable;
  if (sort === 'match_score') return score || recent || stable;
  if (sort === 'date_found') return recent || score || stable;
  return String(a[sort] || '').localeCompare(String(b[sort] || '')) || score || recent || stable;
}
