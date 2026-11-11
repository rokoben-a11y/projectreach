#include "../port/shared/hp_control_layout.h"

#include <stdio.h>

static const hp_layout_request VECTORS[] = {
    {.safe_x = 0, .safe_y = 0, .safe_w = 844, .safe_h = 390, .control_size = 1, .ring_spacing = 1, .left_handed = 0},
    {.safe_x = 47, .safe_y = 0, .safe_w = 780, .safe_h = 340, .control_size = 1, .ring_spacing = 1, .left_handed = 0},
    {.safe_x = 0, .safe_y = 12, .safe_w = 360, .safe_h = 640, .control_size = 1, .ring_spacing = 0, .left_handed = 0},
    {.safe_x = 0, .safe_y = 0, .safe_w = 900, .safe_h = 620, .control_size = 1, .ring_spacing = 1, .left_handed = 0},
    {.safe_x = 20, .safe_y = 8, .safe_w = 1180, .safe_h = 820, .control_size = 1, .ring_spacing = 1, .left_handed = 0},
    {.safe_x = 0, .safe_y = 0, .safe_w = 699.5, .safe_h = 800, .control_size = 1, .ring_spacing = 1, .left_handed = 0},
    {.safe_x = 0, .safe_y = 0, .safe_w = 700, .safe_h = 500, .control_size = 1, .ring_spacing = 1, .left_handed = 0},
    {.safe_x = 0, .safe_y = 0, .safe_w = 700, .safe_h = 499.5, .control_size = 1, .ring_spacing = 1, .left_handed = 0},
    {.safe_x = 47, .safe_y = 0, .safe_w = 780, .safe_h = 340, .control_size = 1, .ring_spacing = 1, .left_handed = 1},
    {.safe_x = 0, .safe_y = 0, .safe_w = 844, .safe_h = 390, .control_size = 1.35, .ring_spacing = 2, .left_handed = 0},
    {.safe_x = 0, .safe_y = 0, .safe_w = 1024, .safe_h = 768, .control_size = 0.7, .ring_spacing = 0, .left_handed = 1},
    /* Open inner display, landscape, safe rect after the home indicator and trailing status column. */
    {.safe_x = 0, .safe_y = 0, .safe_w = 867, .safe_h = 635, .control_size = 1, .ring_spacing = 1, .left_handed = 0, .bottom_band = 0},
    {.safe_x = 0, .safe_y = 0, .safe_w = 867, .safe_h = 635, .control_size = 1, .ring_spacing = 1, .left_handed = 0, .bottom_band = 1},
};

int main(void)
{
    unsigned v, i;
    printf("{\"policy\":\"%s\",\"version\":%d,\"large_min_safe_width\":%.0f,\"large_min_safe_height\":%.0f,\"minimum_target_points\":%.0f,\"slots\":%d,\"vectors\":[",
           HP_LAYOUT_POLICY_ID, HP_LAYOUT_POLICY_VERSION, HP_LAYOUT_LARGE_MIN_WIDTH, HP_LAYOUT_LARGE_MIN_HEIGHT,
           HP_LAYOUT_MIN_TARGET, HP_LAYOUT_SLOT_COUNT);
    for (v = 0; v < sizeof VECTORS / sizeof VECTORS[0]; v++) {
        const hp_layout_request *req = &VECTORS[v];
        hp_layout_box boxes[HP_LAYOUT_SLOT_COUNT];
        hp_layout_frames(req, boxes);
        if (v) printf(",");
        printf("{\"safe\":[%.4f,%.4f,%.4f,%.4f],\"control_size\":%.2f,\"ring_spacing\":%d,\"left_handed\":%d,\"bottom_band\":%d,\"size_class\":\"%s\",\"frames\":[",
               req->safe_x, req->safe_y, req->safe_w, req->safe_h, req->control_size, req->ring_spacing, req->left_handed,
               req->bottom_band,
               hp_layout_size_class(req->safe_w, req->safe_h) == HP_LAYOUT_LARGE ? "large" : "compact");
        for (i = 0; i < HP_LAYOUT_SLOT_COUNT; i++) {
            if (i) printf(",");
            printf("[%.4f,%.4f,%.4f,%.4f]", boxes[i].x, boxes[i].y, boxes[i].w, boxes[i].h);
        }
        printf("]}");
    }
    printf("],\"avoidance\":[");
    {
        const hp_layout_region fold_cases[][2] = {
            {{455.5, 0, 40, 669}, {867, 0, 84, 124}},
            {{0, 300, 867, 40}, {0, 0, 0, 0}},
        };
        const int counts[] = {2, 1};
        unsigned c, i;
        for (c = 0; c < 2; c++) {
            hp_layout_request req = {.safe_x = 0, .safe_y = 0, .safe_w = 867, .safe_h = 635,
                                    .control_size = 1, .ring_spacing = 1, .left_handed = 0, .bottom_band = 1};
            hp_layout_box boxes[HP_LAYOUT_SLOT_COUNT];
            hp_layout_place(req, fold_cases[c], counts[c], boxes);
            if (c) printf(",");
            printf("{\"regions\":[");
            for (i = 0; i < (unsigned)counts[c]; i++) {
                if (i) printf(",");
                printf("[%.4f,%.4f,%.4f,%.4f]", fold_cases[c][i].x, fold_cases[c][i].y,
                       fold_cases[c][i].w, fold_cases[c][i].h);
            }
            printf("],\"frames\":[");
            for (i = 0; i < HP_LAYOUT_SLOT_COUNT; i++) {
                if (i) printf(",");
                printf("[%.4f,%.4f,%.4f,%.4f]", boxes[i].x, boxes[i].y, boxes[i].w, boxes[i].h);
            }
            printf("]}");
        }
    }
    printf("]}\n");
    return 0;
}
