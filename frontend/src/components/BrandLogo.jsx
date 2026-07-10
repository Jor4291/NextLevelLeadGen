import { useAuth } from "../auth";

export default function BrandLogo({ variant = "sidebar", className = "" }) {
  const { brand } = useAuth();
  const src = brand?.logo_url || "/nextlevel-logo.png";
  const alt = brand?.display_name || "Next Level Studio";

  return (
    <img
      src={src}
      alt={alt}
      className={`brand-logo brand-logo--${variant} ${className}`.trim()}
    />
  );
}
