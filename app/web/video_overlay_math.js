(function (globalScope) {
  function getVideoContentBox(containerWidth, containerHeight, videoWidth, videoHeight) {
    const safeContainerWidth = Number(containerWidth || 0);
    const safeContainerHeight = Number(containerHeight || 0);
    const safeVideoWidth = Number(videoWidth || 0);
    const safeVideoHeight = Number(videoHeight || 0);

    if (!safeContainerWidth || !safeContainerHeight || !safeVideoWidth || !safeVideoHeight) {
      return null;
    }

    const videoAspect = safeVideoWidth / safeVideoHeight;
    const containerAspect = safeContainerWidth / safeContainerHeight;

    if (containerAspect > videoAspect) {
      const height = safeContainerHeight;
      const width = height * videoAspect;
      return {
        left: (safeContainerWidth - width) / 2,
        top: 0,
        width,
        height,
      };
    }

    const width = safeContainerWidth;
    const height = width / videoAspect;
    return {
      left: 0,
      top: (safeContainerHeight - height) / 2,
      width,
      height,
    };
  }

  function clamp01(value) {
    return Math.min(Math.max(Number(value || 0), 0), 1);
  }

  function mapNormalizedPointToDisplay(point, contentBox) {
    if (!contentBox || !point) {
      return null;
    }

    return {
      x: contentBox.left + (clamp01(point.x) * contentBox.width),
      y: contentBox.top + (clamp01(point.y) * contentBox.height),
    };
  }

  function mapNormalizedRectToDisplay(rect, contentBox) {
    if (!contentBox || !rect) {
      return null;
    }

    const x1 = contentBox.left + (clamp01(rect.x1) * contentBox.width);
    const y1 = contentBox.top + (clamp01(rect.y1) * contentBox.height);
    const x2 = contentBox.left + (clamp01(rect.x2) * contentBox.width);
    const y2 = contentBox.top + (clamp01(rect.y2) * contentBox.height);
    return {
      x1,
      y1,
      x2,
      y2,
      width: Math.max(x2 - x1, 1),
      height: Math.max(y2 - y1, 1),
    };
  }

  const api = {
    getVideoContentBox,
    mapNormalizedPointToDisplay,
    mapNormalizedRectToDisplay,
  };

  globalScope.AnalysisOverlayMath = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
