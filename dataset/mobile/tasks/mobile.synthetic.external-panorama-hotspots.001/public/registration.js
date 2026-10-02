import {wrap} from './geometry.js';
// Adapter between imported review records and the stitched panorama camera.
export function reviewToPanorama(review,capture) {
  return {yaw:wrap(review.azimuth),pitch:review.elevation};
}
export function panoramaToReview(point,capture) {
  return {azimuth:wrap(point.yaw),elevation:point.pitch};
}
