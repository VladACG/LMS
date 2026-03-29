import type { StudentInput } from '../types/lms';

export function parseStudentsInput(input: string): StudentInput[] {
  const unique = new Set<string>();
  const rows: StudentInput[] = [];

  input
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const [namePart, emailPart] = line.split(',').map((chunk) => chunk.trim());
      if (!namePart) {
        return;
      }

      const email = emailPart || undefined;
      const key = `${namePart.toLowerCase()}::${(email ?? '').toLowerCase()}`;
      if (unique.has(key)) {
        return;
      }

      unique.add(key);
      rows.push({ full_name: namePart, email });
    });

  return rows;
}
