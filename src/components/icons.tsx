/** Small stroke icons (lucide-style paths, inlined: no icon package). */
const P: Record<string, React.ReactNode> = {
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  inbox: <><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" /></>,
  gaps: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><path d="M14 17.5h7" strokeDasharray="2 2" /></>,
  folder: <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />,
  folderOpen: <path d="m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5c0-1.1.9-2 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H18a2 2 0 0 1 2 2v2" />,
  view: <><path d="M3 6h18" /><path d="M7 12h10" /><path d="M10 18h4" /></>,
  pin: <><path d="M12 17v5" /><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z" /></>,
  more: <><circle cx="5" cy="12" r="1.2" /><circle cx="12" cy="12" r="1.2" /><circle cx="19" cy="12" r="1.2" /></>,
  plus: <><path d="M12 5v14" /><path d="M5 12h14" /></>,
  chevRight: <path d="m9 18 6-6-6-6" />,
  chevDown: <path d="m6 9 6 6 6-6" />,
  panelClose: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 3v18" /><path d="m16 15-3-3 3-3" /></>,
  panelOpen: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 3v18" /><path d="m14 9 3 3-3 3" /></>,
  tag: <><path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" /><circle cx="7.5" cy="7.5" r=".5" /></>,
  filter: <path d="M22 3H2l8 9.46V19l4 2v-8.54z" />,
  columns: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 3v18" /><path d="M15 3v18" /></>,
  download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m7 10 5 5 5-5" /><path d="M12 15V3" /></>,
  x: <><path d="M18 6 6 18" /><path d="m6 6 12 12" /></>,
  external: <><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></>,
};
export type IconName = keyof typeof P;

export function Icon({ name, className }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {P[name]}
    </svg>
  );
}

export function Emblem() {
  return (
    <svg className="emblem" viewBox="0 0 62 62" fill="none" aria-hidden="true">
      <path fill="currentColor" d="M31.0002 62.0003L0.000103335 31.0001L31.0002 0L62.0004 31.0001L31.0002 62.0003ZM35.1573 16.4609L31.3048 27.2022H31.1377L27.2852 16.4609L20.1671 20.2009L28.0385 28.8733L27.9557 29.0321L16.8174 26.6456V34.7608L27.8714 32.5331L27.955 32.6926L20.1678 41.1261L27.2016 45.1837L31.0534 34.363L31.2212 34.3637L35.073 45.1844L42.1917 41.1261L34.4032 32.6926L34.4868 32.5331L45.5408 34.7608V26.6456L34.3203 28.9527L34.2361 28.8726L42.1917 20.2002L35.1573 16.4609Z" />
    </svg>
  );
}
