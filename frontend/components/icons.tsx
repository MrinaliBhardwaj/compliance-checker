// Inline icon set — no icon dependency, so the bundle stays small and the app
// renders identically offline. 16px grid, 1.5 stroke, currentColor.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 15, children, ...rest }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      focusable="false" {...rest}>
      {children}
    </svg>
  );
}

export const IconHome = (p: P) => (
  <Svg {...p}><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></Svg>
);
export const IconList = (p: P) => (
  <Svg {...p}><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" /></Svg>
);
export const IconFile = (p: P) => (
  <Svg {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></Svg>
);
export const IconGavel = (p: P) => (
  <Svg {...p}><path d="M3 21h9" /><path d="m6 15 6-6" /><path d="m10.5 4.5 5 5" /><path d="m13 2 7 7" /><path d="m15.5 7.5-5 5" /></Svg>
);
export const IconChart = (p: P) => (
  <Svg {...p}><path d="M3 3v18h18" /><path d="M7 15v3M12 10v8M17 6v12" /></Svg>
);
export const IconShield = (p: P) => (
  <Svg {...p}><path d="M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Svg>
);
export const IconUsers = (p: P) => (
  <Svg {...p}><circle cx="9" cy="8" r="3.2" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16.5 5.3a3.2 3.2 0 0 1 0 5.4M18 14.4a6.5 6.5 0 0 1 3.5 5.6" /></Svg>
);
export const IconBell = (p: P) => (
  <Svg {...p}><path d="M18 8.5a6 6 0 1 0-12 0c0 6-2.5 7.5-2.5 7.5h17S18 14.5 18 8.5" /><path d="M10.3 20a2 2 0 0 0 3.4 0" /></Svg>
);
export const IconSearch = (p: P) => (
  <Svg {...p}><circle cx="10.5" cy="10.5" r="6.5" /><path d="m20 20-4.5-4.5" /></Svg>
);
export const IconClock = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5.2l3.2 2" /></Svg>
);
export const IconAlert = (p: P) => (
  <Svg {...p}><path d="M12 3.5 1.8 20.5h20.4L12 3.5Z" /><path d="M12 10v4.2" /><path d="M12 17.6h.01" /></Svg>
);
export const IconCheck = (p: P) => (
  <Svg {...p}><path d="m4.5 12.5 5 5 10-11" /></Svg>
);
export const IconCheckCircle = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="m8 12.2 2.6 2.6L16 9.4" /></Svg>
);
export const IconXCircle = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="m9 9 6 6M15 9l-6 6" /></Svg>
);
export const IconX = (p: P) => (
  <Svg {...p}><path d="M5 5l14 14M19 5 5 19" /></Svg>
);
export const IconInfo = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5" /><path d="M12 7.6h.01" /></Svg>
);
export const IconChevronRight = (p: P) => (
  <Svg {...p}><path d="m9 5 7 7-7 7" /></Svg>
);
export const IconChevronDown = (p: P) => (
  <Svg {...p}><path d="m5 9 7 7 7-7" /></Svg>
);
export const IconArrowUp = (p: P) => (
  <Svg {...p}><path d="M12 20V4M5.5 10.5 12 4l6.5 6.5" /></Svg>
);
export const IconArrowDown = (p: P) => (
  <Svg {...p}><path d="M12 4v16M5.5 13.5 12 20l6.5-6.5" /></Svg>
);
export const IconArrowRight = (p: P) => (
  <Svg {...p}><path d="M4 12h16M13.5 5.5 20 12l-6.5 6.5" /></Svg>
);
export const IconUndo = (p: P) => (
  <Svg {...p}><path d="M4 9h11a5 5 0 0 1 0 10H8" /><path d="M8 5 4 9l4 4" /></Svg>
);
export const IconUpload = (p: P) => (
  <Svg {...p}><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></Svg>
);
export const IconDownload = (p: P) => (
  <Svg {...p}><path d="M12 4v12" /><path d="m7 11 5 5 5-5" /><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></Svg>
);
export const IconUser = (p: P) => (
  <Svg {...p}><circle cx="12" cy="8" r="3.4" /><path d="M4.5 20a7.5 7.5 0 0 1 15 0" /></Svg>
);
export const IconSparkle = (p: P) => (
  <Svg {...p}><path d="M12 3.5 13.7 9l5.3 1.7-5.3 1.7L12 18l-1.7-5.6L5 10.7 10.3 9 12 3.5Z" /><path d="M18.5 16.5 19 18l1.5.5L19 19l-.5 1.5L18 19l-1.5-.5L18 18l.5-1.5Z" /></Svg>
);
export const IconSun = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4" /></Svg>
);
export const IconMoon = (p: P) => (
  <Svg {...p}><path d="M20 14.2A8.5 8.5 0 0 1 9.8 4 8.5 8.5 0 1 0 20 14.2Z" /></Svg>
);
export const IconLogout = (p: P) => (
  <Svg {...p}><path d="M14 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8" /><path d="M17 8.5 20.5 12 17 15.5" /><path d="M20.5 12H10" /></Svg>
);
export const IconInbox = (p: P) => (
  <Svg {...p}><path d="M3 13h4.5l1.5 3h6l1.5-3H21" /><path d="M5.2 5h13.6l2.2 8v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5l2.2-8Z" /></Svg>
);
export const IconFilter = (p: P) => (
  <Svg {...p}><path d="M3.5 5h17l-6.7 7.8V19l-3.6 2v-8.2L3.5 5Z" /></Svg>
);
export const IconBuilding = (p: P) => (
  <Svg {...p}><path d="M4 21V5.5a1.5 1.5 0 0 1 1.5-1.5h7A1.5 1.5 0 0 1 14 5.5V21" /><path d="M14 10h4.5A1.5 1.5 0 0 1 20 11.5V21" /><path d="M2.5 21h19" /><path d="M7.5 8h3M7.5 12h3M7.5 16h3M17 14h.01M17 17.5h.01" /></Svg>
);
export const IconPaperclip = (p: P) => (
  <Svg {...p}><path d="M20 11.5 12 19.5a5 5 0 0 1-7-7l8.5-8.5a3.5 3.5 0 0 1 5 5L10.4 17a2 2 0 0 1-3-3l7.6-7.6" /></Svg>
);
export const IconMore = (p: P) => (
  <Svg {...p}><circle cx="5" cy="12" r="1.4" fill="currentColor" /><circle cx="12" cy="12" r="1.4" fill="currentColor" /><circle cx="19" cy="12" r="1.4" fill="currentColor" /></Svg>
);
export const IconMinus = (p: P) => (
  <Svg {...p}><path d="M5 12h14" /></Svg>
);
export const IconPlay = (p: P) => (
  <Svg {...p}><path d="M7 4.5v15l13-7.5-13-7.5Z" /></Svg>
);
export const IconBan = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="m5.6 5.6 12.8 12.8" /></Svg>
);
export const IconLock = (p: P) => (
  <Svg {...p}><rect x="4.5" y="10.5" width="15" height="10" rx="2" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></Svg>
);
export const IconExternal = (p: P) => (
  <Svg {...p}><path d="M14 4h6v6" /><path d="M20 4 11 13" /><path d="M18 14.5V19a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 19V8a1.5 1.5 0 0 1 1.5-1.5H10" /></Svg>
);
export const IconCalendar = (p: P) => (
  <Svg {...p}><rect x="3.5" y="5" width="17" height="16" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></Svg>
);
