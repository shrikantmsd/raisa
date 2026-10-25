import { redirect } from "next/navigation";

export default function Home() {
  // Layer 1 has no public marketing page yet — every visit goes to the
  // authenticated shell's entry point. /login itself decides whether to
  // bounce further to /dashboard once a token already exists.
  redirect("/login");
}
