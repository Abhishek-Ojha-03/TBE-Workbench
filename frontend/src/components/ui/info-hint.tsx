export default function InfoHint({ text }: { text: string }) {
  return (
    <span
      title={text}
      className="ml-1 inline-flex h-3.5 w-3.5 shrink-0 cursor-help items-center justify-center rounded-full border border-neutral-100 align-middle text-[9px] font-medium leading-none text-neutral-100"
    >
      i
    </span>
  );
}
