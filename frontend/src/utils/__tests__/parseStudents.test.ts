import { describe, expect, it } from 'vitest';

import { parseStudentsInput } from '../parseStudents';

describe('parseStudentsInput', () => {
  it('parses rows and removes duplicates', () => {
    const rows = parseStudentsInput('Иван Иванов,ivan@example.com\nИван Иванов,ivan@example.com\nМария Петрова');

    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({ full_name: 'Иван Иванов', email: 'ivan@example.com' });
    expect(rows[1]).toEqual({ full_name: 'Мария Петрова', email: undefined });
  });

  it('ignores blank lines', () => {
    const rows = parseStudentsInput('\n \nПетр Петров\n');
    expect(rows).toEqual([{ full_name: 'Петр Петров', email: undefined }]);
  });
});
