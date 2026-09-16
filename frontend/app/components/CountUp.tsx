"use client";

/**
 * CountUp — animates a number from 0 to `value` when it mounts / changes,
 * so result figures tick up instead of snapping in. Uses Framer Motion's
 * animate() with a motion value.
 *
 * `format` lets the caller control how the running number is rendered
 * (e.g. add ₹ and Indian-style grouping).
 */
import { useEffect, useState } from "react";
import { animate } from "framer-motion";

interface CountUpProps {
  value: number;
  duration?: number;
  format?: (n: number) => string;
}

export default function CountUp({
  value,
  duration = 1.1,
  format = (n) => Math.round(n).toLocaleString("en-IN"),
}: CountUpProps) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    // animate from the current displayed value up to the target.
    const controls = animate(0, value, {
      duration,
      ease: "easeOut",
      onUpdate: (v) => setDisplay(v),
    });
    return () => controls.stop();
  }, [value, duration]);

  return <>{format(display)}</>;
}
