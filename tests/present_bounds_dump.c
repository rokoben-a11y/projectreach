#include "../port/shared/hp_present.h"

#include <stdio.h>

static void dump(const char *name, double vw, double vh, double sw, double sh, int fit)
{
    double x, y, w, h;
    hp_present_frame(vw, vh, sw, sh, fit, &x, &y, &w, &h);
    printf("{\"name\":\"%s\",\"view\":[%.4f,%.4f],\"source\":[%.4f,%.4f],\"fit\":%d,\"frame\":[%.4f,%.4f,%.4f,%.4f]}\n",
           name, vw, vh, sw, sh, fit, x, y, w, h);
}

int main(void)
{
    dump("wide-fill", 1100, 700, 640, 480, 0);
    dump("wide-fit", 1100, 700, 640, 480, 1);
    dump("phone-fill", 844, 390, 640, 480, 0);
    dump("phone-fit", 844, 390, 640, 480, 1);
    dump("tall-fill", 390, 844, 800, 600, 0);
    dump("inner-fill", 900, 620, 640, 480, 0);
    dump("inner-fit", 900, 620, 640, 480, 1);
    return 0;
}
