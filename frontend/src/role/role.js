const ROLE_KEY = 'postcards_role_v1';
const VALID = /^pc[1-4]$/;

export function getRole() {
  // Приоритет: localStorage -> ?role= (дев) -> pc1
  const stored = localStorage.getItem(ROLE_KEY);
  if (VALID.test(stored || '')) return stored;
  const q = new URLSearchParams(location.search).get('role');
  if (VALID.test(q || '')) return q;
  return 'pc1';
}

export function setRole(role) {
  if (!VALID.test(role)) return;
  localStorage.setItem(ROLE_KEY, role);
  // Роль влияет на всё (ws identify, pdf-резолвер) — честнее перезагрузить.
  location.reload();
}

export const ROLES_LIST = ['pc1', 'pc2', 'pc3', 'pc4'];