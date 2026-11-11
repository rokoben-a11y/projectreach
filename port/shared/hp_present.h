/* Where a source image sits in the current view. No device sizes.
   fit=0 scales to the whole view. fit=1 letterboxes with one scale. */
#ifndef HP_PRESENT_H
#define HP_PRESENT_H

static inline void hp_present_frame(double view_w, double view_h, double src_w, double src_h,
                                    int fit, double *x, double *y, double *w, double *h)
{
    if (!(view_w > 0.0 && view_h > 0.0)) {
        *x = *y = *w = *h = 0.0;
        return;
    }
    if (!fit || !(src_w > 0.0 && src_h > 0.0)) {
        *x = *y = 0.0;
        *w = view_w;
        *h = view_h;
        return;
    }
    double scale = view_w / src_w;
    double by_height = view_h / src_h;
    if (by_height < scale) scale = by_height;
    *w = src_w * scale;
    *h = src_h * scale;
    *x = (view_w - *w) / 2.0;
    *y = (view_h - *h) / 2.0;
}

#endif
