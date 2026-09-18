import http from "k6/http";
import { check, fail } from "k6";
import { Rate, Trend } from "k6/metrics";

const target = (__ENV.TARGET_URL || "http://127.0.0.1:7860").replace(/\/$/, "");
const duration = __ENV.LOAD_DURATION || "5m";
const replyVisible = new Trend("reply_visible_ms");
const generatedReply = new Rate("generated_reply");
const queueSaturation = new Rate("queue_saturation");

export const options = {
  scenarios: {
    chat_release_candidate: {
      executor: "constant-vus",
      vus: 50,
      duration,
    },
  },
  thresholds: {
    reply_visible_ms: ["p(95)<10000"],
    generated_reply: ["rate==1"],
    queue_saturation: ["rate==0"],
  },
};

function readCompleteEvent(response) {
  const dataLine = response.body
    .split("\n")
    .find((line) => line.startsWith("data: "));
  if (!dataLine || !response.body.includes("event: complete")) {
    return null;
  }
  return JSON.parse(dataLine.slice("data: ".length));
}

export default function () {
  const message = `load-${__VU}-${__ITER}`;
  const startedAt = Date.now();
  const submit = http.post(
    `${target}/gradio_api/call/submit`,
    JSON.stringify({ data: [message, null] }),
    { headers: { "Content-Type": "application/json" } },
  );

  const accepted = check(submit, {
    "submit accepted": (response) => response.status === 200 && Boolean(response.json("event_id")),
  });
  queueSaturation.add(!accepted && (submit.status === 429 || submit.status === 503));
  if (!accepted) {
    fail(`Chat submission was not accepted (HTTP ${submit.status}).`);
  }

  const eventId = submit.json("event_id");
  const completed = http.get(`${target}/gradio_api/call/submit/${eventId}`);
  const payload = readCompleteEvent(completed);
  const messages = payload && payload[0];
  const responseText =
    messages &&
    messages.length === 2 &&
    messages[1].content &&
    messages[1].content[0] &&
    messages[1].content[0].text;
  const isGenerated = messages && messages[0].content[0].text === message && responseText && responseText !== message;

  replyVisible.add(Date.now() - startedAt);
  generatedReply.add(Boolean(isGenerated));
  queueSaturation.add(completed.status === 429 || completed.status === 503);
  check(completed, {
    "chat event completed": (response) => response.status === 200 && Boolean(payload),
    "one generated user and assistant pair": () => Boolean(isGenerated),
  });
}
