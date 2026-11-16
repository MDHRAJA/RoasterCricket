/** Display aliases only; this does not alter historical team records. */
export const teams = {
  CSK: { name: 'Chennai Super Kings', short: 'Chennai', color: '#EBC200', ink: '#16171A' },
  DC: { name: 'Delhi Capitals', short: 'Delhi', color: '#245CAA', ink: '#FFFFFF' },
  GT: { name: 'Gujarat Titans', short: 'Gujarat', color: '#234D50', ink: '#FFFFFF' },
  KKR: { name: 'Kolkata Knight Riders', short: 'Kolkata', color: '#564681', ink: '#FFFFFF' },
  LSG: { name: 'Lucknow Super Giants', short: 'Lucknow', color: '#006A84', ink: '#FFFFFF' },
  MI: { name: 'Mumbai Indians', short: 'Mumbai', color: '#0070B5', ink: '#FFFFFF' },
  PBKS: { name: 'Punjab Kings', short: 'Punjab', color: '#AF212B', ink: '#FFFFFF' },
  RR: { name: 'Rajasthan Royals', short: 'Rajasthan', color: '#B52765', ink: '#FFFFFF' },
  RCB: {
    name: 'Royal Challengers Bengaluru',
    short: 'Bengaluru',
    color: '#C12B31',
    ink: '#FFFFFF',
  },
  SRH: { name: 'Sunrisers Hyderabad', short: 'Hyderabad', color: '#BB481A', ink: '#FFFFFF' },
} as const;

export function team(id: string) {
  return (
    teams[id as keyof typeof teams] ?? { name: id, short: id, color: '#61625E', ink: '#FFFFFF' }
  );
}
