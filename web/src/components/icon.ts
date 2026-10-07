/** Shared lucide props: 16px inline, stroke 1.75, decorative (text always carries the meaning). */
export const ICON = { size: 16, strokeWidth: 1.75, 'aria-hidden': true } as const;

/** Navigation icons are one step larger. */
export const NAV_ICON = { ...ICON, size: 18 } as const;
