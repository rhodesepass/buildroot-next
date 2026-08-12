/*
 * Enumerate what the cedrus V4L2 device actually offers, and what layout it
 * settles on for a given decode setup. Exists because the board has no
 * v4l2-utils and the question "can the VE write something the mixer can
 * scan out" has to be answered on hardware, not from the driver source.
 *
 * Usage: cedrus-probe [/dev/videoN]
 */
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <linux/videodev2.h>

static void fourcc(char out[5], unsigned int f)
{
	out[0] = f & 0xff;
	out[1] = (f >> 8) & 0xff;
	out[2] = (f >> 16) & 0xff;
	out[3] = (f >> 24) & 0xff;
	out[4] = 0;
}

static void enum_formats(int fd, unsigned int type, const char *label)
{
	struct v4l2_fmtdesc d;
	char cc[5];

	printf("%s:\n", label);
	for (d.index = 0;; d.index++) {
		memset(&d.type, 0, sizeof(d) - sizeof(d.index));
		d.type = type;
		if (ioctl(fd, VIDIOC_ENUM_FMT, &d) < 0)
			break;
		fourcc(cc, d.pixelformat);
		printf("  [%u] %s  %s\n", d.index, cc, d.description);
	}
	if (d.index == 0)
		printf("  (none)\n");
}

static int try_capture(int fd, unsigned int pixfmt, int w, int h)
{
	struct v4l2_format f;
	char cc[5];

	memset(&f, 0, sizeof(f));
	f.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	f.fmt.pix.width = w;
	f.fmt.pix.height = h;
	f.fmt.pix.pixelformat = pixfmt;
	f.fmt.pix.field = V4L2_FIELD_NONE;

	fourcc(cc, pixfmt);
	if (ioctl(fd, VIDIOC_TRY_FMT, &f) < 0) {
		printf("  %s: TRY_FMT failed\n", cc);
		return -1;
	}

	fourcc(cc, f.fmt.pix.pixelformat);
	printf("  %s: %ux%u bpl=%u size=%u", cc, f.fmt.pix.width,
	       f.fmt.pix.height, f.fmt.pix.bytesperline, f.fmt.pix.sizeimage);
	if (f.fmt.pix.pixelformat != pixfmt)
		printf("   <-- NOT the format asked for");
	printf("\n");

	return 0;
}

int main(int argc, char **argv)
{
	const char *path = argc > 1 ? argv[1] : "/dev/video0";
	struct v4l2_capability cap;
	struct v4l2_format out;
	int fd;

	fd = open(path, O_RDWR);
	if (fd < 0) {
		perror(path);
		return 1;
	}

	if (ioctl(fd, VIDIOC_QUERYCAP, &cap) < 0) {
		perror("QUERYCAP");
		return 1;
	}
	printf("driver=%s card=%s caps=%08x\n\n", cap.driver, cap.card,
	       cap.device_caps);

	enum_formats(fd, V4L2_BUF_TYPE_VIDEO_OUTPUT, "OUTPUT (bitstream)");
	printf("\n");
	enum_formats(fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, "CAPTURE (frames)");

	/*
	 * The capture side only advertises the formats the selected codec can
	 * produce, so pick H.264 first.
	 */
	memset(&out, 0, sizeof(out));
	out.type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
	out.fmt.pix.width = 1280;
	out.fmt.pix.height = 720;
	out.fmt.pix.pixelformat = V4L2_PIX_FMT_H264_SLICE;
	out.fmt.pix.sizeimage = 1024 * 1024;
	out.fmt.pix.field = V4L2_FIELD_NONE;
	printf("\nS_FMT OUTPUT H264_SLICE 1280x720: %s\n",
	       ioctl(fd, VIDIOC_S_FMT, &out) < 0 ? "FAILED" : "ok");

	printf("\nCAPTURE layouts for H.264 at 1280x720:\n");
	try_capture(fd, V4L2_PIX_FMT_NV12, 1280, 720);
	try_capture(fd, V4L2_PIX_FMT_NV12_32L32, 1280, 720);

	printf("\nCAPTURE layouts at 720x1280 (panel-shaped):\n");
	try_capture(fd, V4L2_PIX_FMT_NV12, 720, 1280);

	close(fd);
	return 0;
}
