const assert = require("assert");
const {
  getVideoContentBox,
  mapNormalizedPointToDisplay,
  mapNormalizedRectToDisplay,
} = require("../app/web/video_overlay_math.js");

function testLetterboxedLandscapeVideo() {
  const contentBox = getVideoContentBox(1200, 900, 1280, 720);
  assert.ok(contentBox);
  assert.strictEqual(Math.round(contentBox.left), 0);
  assert.strictEqual(Math.round(contentBox.width), 1200);
  assert.strictEqual(Math.round(contentBox.height), 675);
  assert.strictEqual(Math.round(contentBox.top), 113);

  const point = mapNormalizedPointToDisplay({ x: 0.5, y: 0.5 }, contentBox);
  assert.strictEqual(Math.round(point.x), 600);
  assert.strictEqual(Math.round(point.y), 450);

  const rect = mapNormalizedRectToDisplay(
    { x1: 0.25, y1: 0.2, x2: 0.5, y2: 0.6 },
    contentBox
  );
  assert.strictEqual(Math.round(rect.x1), 300);
  assert.strictEqual(Math.round(rect.y1), 248);
  assert.strictEqual(Math.round(rect.width), 300);
  assert.strictEqual(Math.round(rect.height), 270);
}

function testPillarboxedPortraitVideo() {
  const contentBox = getVideoContentBox(1000, 500, 720, 1280);
  assert.ok(contentBox);
  assert.strictEqual(Math.round(contentBox.top), 0);
  assert.strictEqual(Math.round(contentBox.height), 500);
  assert.strictEqual(Math.round(contentBox.width), 281);
  assert.strictEqual(Math.round(contentBox.left), 359);

  const rect = mapNormalizedRectToDisplay(
    { x1: 0.1, y1: 0.1, x2: 0.4, y2: 0.4 },
    contentBox
  );
  assert.strictEqual(Math.round(rect.x1), 388);
  assert.strictEqual(Math.round(rect.y1), 50);
  assert.strictEqual(Math.round(rect.width), 84);
  assert.strictEqual(Math.round(rect.height), 150);
}

testLetterboxedLandscapeVideo();
testPillarboxedPortraitVideo();
console.log("analysis overlay math tests: ok");
