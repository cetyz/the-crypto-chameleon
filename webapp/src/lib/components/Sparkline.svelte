<script lang="ts">
  let { values, color = '#10b981' }: { values: number[]; color?: string } = $props();

  const width = 140;
  const height = 36;

  const path = $derived.by(() => {
    if (values.length < 2) return '';
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const step = width / (values.length - 1);
    return values
      .map((v, i) => {
        const x = i * step;
        const y = height - ((v - min) / range) * height;
        return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(' ');
  });
</script>

<svg {width} {height} viewBox="0 0 {width} {height}" class="block">
  <path d={path} fill="none" stroke={color} stroke-width="1.5" />
</svg>
