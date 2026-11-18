export interface WordSegment {
  start: number;
  end: number;
  text: string;
  confidence?: number;
}

export interface SentenceSegment {
  id: string;
  start: number;
  end: number;
  text: string;
  words?: WordSegment[];
  asl_status?: string;
}

export function formatTimestamp(seconds: number): string {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const mins = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  const tenths = Math.floor((safe % 1) * 10);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${tenths}`;
}

export function formatClock(seconds: number): string {
  const safe = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export function findActiveSentenceIndex(
  sentences: SentenceSegment[],
  currentTime: number
): number {
  for (let i = 0; i < sentences.length; i += 1) {
    const seg = sentences[i];
    if (currentTime >= seg.start && currentTime <= seg.end + 0.15) {
      return i;
    }
  }
  return -1;
}

export function isSupportedYouTubeUrl(rawUrl: string): boolean {
  try {
    const parsed = new URL((rawUrl || '').trim());
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return false;
    }
    const host = parsed.hostname.toLowerCase();
    const allowedHosts = new Set([
      'youtube.com',
      'www.youtube.com',
      'm.youtube.com',
      'music.youtube.com',
      'youtu.be',
      'www.youtu.be',
    ]);
    return allowedHosts.has(host);
  } catch {
    return false;
  }
}
