import {queryClient} from "./api/queryClient.js";
import {compilePanelPlan} from "./config/compilePanelPlan.js";
import {queryPolicy} from "./config/queryPolicy.js";
import {acceptInitial} from "./controllers/dashboard.js";
import {subscribe, updateState} from "./state/store.js";
import {render} from "./views/render.js";

subscribe(render);

async function start() {
  try {
    const catalog = await queryClient.catalog();
    const plan = compilePanelPlan(queryPolicy());
    updateState({catalog, plan});
    acceptInitial(await queryClient.configure(plan));
  } catch (error) {
    updateState({error: error.message});
  }
}

start();
