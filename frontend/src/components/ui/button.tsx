import { ButtonHTMLAttributes, forwardRef } from "react";

type ButtonVariant = "primary" | "dark" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

// Matches the Figma Design System "Objects" panel: two button families
// (violet-filled, black-filled), each with Normal/Hover/Pressed/Disabled
// states. Pressed/Disabled are handled via Tailwind's active:/disabled:
// variants rather than separate manual states.
const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-violet-300 text-white hover:bg-violet-400 active:bg-violet-500 disabled:bg-violet-100 disabled:text-white/70",
  dark: "bg-neutral-500 text-white hover:bg-neutral-400 active:bg-neutral-300 disabled:bg-neutral-100",
  ghost:
    "bg-transparent text-neutral-200 hover:bg-neutral-50 active:bg-neutral-50 disabled:text-neutral-75",
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", className = "", children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={`inline-flex items-center justify-center gap-1 rounded-md px-5 py-2.5 text-b2 font-medium transition-colors disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${className}`}
        {...props}
      >
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";

export default Button;
