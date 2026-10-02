import { groupPixelWidth } from "./size-service.js";

export function measureDashboardGroups(container, groupConfig) {
  const elementsById = new Map(
    [...container.querySelectorAll("[data-dashboard-group]")].map((element) => [
      element.dataset.groupId,
      element
    ])
  );

  return groupConfig.map((group) => {
    const element = elementsById.get(group.id);
    if (!element) {
      throw new Error(`Dashboard group ${group.id} is not mounted`);
    }

    return {
      id: group.id,
      element,
      width: groupPixelWidth(group.columns),
      height: element.offsetHeight
    };
  });
}
