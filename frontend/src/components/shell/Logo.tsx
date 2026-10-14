/** Abstract orbit mark: a lavender core with one inclined orbit and a satellite. */
export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="0.5" y="0.5" width="23" height="23" rx="6.5" fill="#1B1526" stroke="#3A3350" />
      <ellipse cx="12" cy="12" rx="8" ry="3.5" transform="rotate(-28 12 12)" stroke="#A78BFA" strokeOpacity="0.6" strokeWidth="1.3" />
      <circle cx="12" cy="12" r="2.7" fill="#A78BFA" />
      <circle cx="18.3" cy="8.4" r="1.4" fill="#F3F4F6" />
    </svg>
  );
}
