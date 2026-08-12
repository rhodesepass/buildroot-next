/*
 * Drive the sun8i-rotate m2m node with a frame whose four corners are
 * distinguishable, read the result back, and say which transform the hardware
 * actually performed. Exists because the board has no v4l2-utils, and because
 * two questions about this IP cannot be answered from any datasheet:
 *
 *   - is [5:4] in GLB_CTL clockwise or counter-clockwise? The DE2.0 spec says
 *     clockwise; the f1c side has carried "unverified, flip to 270 if wrong"
 *     for its own (different) rotate unit ever since.
 *   - can a YUV frame come back out semi-planar? DE2.0 Spec 5.13.4 says every
 *     YUV input leaves as YUV420 *planar*, the vendor g2d_rotate.c says only
 *     4:2:2 gets downsampled and NV12 passes through unchanged. The driver
 *     currently sides with the spec, so CAPTURE comes back as YU12; this tool
 *     reads whatever G_FMT reports and handles both layouts.
 *
 * Usage: rot-probe [angle] [hflip] [vflip] [dumpfile]
 * Exit:  0 verdict printed, 1 setup failed, 2 hardware did not finish.
 */
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <linux/videodev2.h>

#define SRC_W	128
#define SRC_H	96
#define BLK	32		/* corner block edge */

/* TL, TR, BL, BR -- far enough apart to survive any chroma resampling */
static const unsigned char corner_val[4] = { 240, 16, 80, 176 };
static const char *corner_name[4] = { "TL", "TR", "BL", "BR" };

struct plane {
	unsigned char *base;
	unsigned int stride;
};

/*
 * The capture queue has min_queued_buffers = 2, so both buffers have to be
 * queued before vb2 will start it -- with only one queued, STREAMON succeeds,
 * the m2m job is never scheduled, device_run() never runs, and the symptom is
 * an unexplained timeout with every rotate register still reading zero.
 */
#define CAP_BUFS	2

struct frame {
	unsigned char *map[CAP_BUFS];
	unsigned int length;
	unsigned int nbufs;
	unsigned int width, height;
	unsigned int bytesperline;
	unsigned int sizeimage;
	unsigned int pixfmt;
	struct plane luma;
};

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
	unsigned int n = 0;

	printf("%s:", label);
	for (d.index = 0;; d.index++) {
		memset(&d.type, 0, sizeof(d) - sizeof(d.index));
		d.type = type;
		if (ioctl(fd, VIDIOC_ENUM_FMT, &d) < 0)
			break;
		fourcc(cc, d.pixelformat);
		printf(" %s", cc);
		n++;
	}
	printf("%s\n", n ? "" : " (none)");
}

static int find_device(char *path, unsigned int len)
{
	struct v4l2_capability cap;
	char p[32];
	int i, fd;

	for (i = 0; i < 16; i++) {
		snprintf(p, sizeof(p), "/dev/video%d", i);
		fd = open(p, O_RDWR);
		if (fd < 0)
			continue;
		memset(&cap, 0, sizeof(cap));
		if (ioctl(fd, VIDIOC_QUERYCAP, &cap) == 0 &&
		    strcmp((const char *)cap.card, "sun8i-rotate") == 0) {
			snprintf(path, len, "%s", p);
			printf("found %s: driver=%s card=%s\n", p, cap.driver,
			       cap.card);
			return fd;
		}
		close(fd);
	}
	fprintf(stderr, "no sun8i-rotate device found\n");
	return -1;
}

static int set_ctrl(int fd, unsigned int id, int value, const char *what)
{
	struct v4l2_control c = { .id = id, .value = value };

	if (ioctl(fd, VIDIOC_S_CTRL, &c) < 0) {
		fprintf(stderr, "S_CTRL %s=%d failed: %m\n", what, value);
		return -1;
	}
	return 0;
}

static int setup_side(int fd, unsigned int type, unsigned int w, unsigned int h,
		      struct frame *f, const char *label)
{
	struct v4l2_requestbuffers req;
	struct v4l2_buffer buf;
	struct v4l2_format fmt;
	unsigned int i;
	char cc[5];

	memset(&fmt, 0, sizeof(fmt));
	fmt.type = type;
	fmt.fmt.pix.width = w;
	fmt.fmt.pix.height = h;
	fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_NV12;
	fmt.fmt.pix.field = V4L2_FIELD_NONE;

	/*
	 * CAPTURE geometry and format are derived by the driver from the
	 * OUTPUT side plus the rotate control, and whatever we pass here is
	 * overwritten. S_FMT still has to be called, and its result is the
	 * layout we must read back with.
	 */
	if (ioctl(fd, VIDIOC_S_FMT, &fmt) < 0) {
		fprintf(stderr, "%s S_FMT failed: %m\n", label);
		return -1;
	}

	f->width = fmt.fmt.pix.width;
	f->height = fmt.fmt.pix.height;
	f->bytesperline = fmt.fmt.pix.bytesperline;
	f->sizeimage = fmt.fmt.pix.sizeimage;
	f->pixfmt = fmt.fmt.pix.pixelformat;

	fourcc(cc, f->pixfmt);
	printf("%-7s %s %ux%u bpl=%u size=%u\n", label, cc, f->width, f->height,
	       f->bytesperline, f->sizeimage);

	f->nbufs = V4L2_TYPE_IS_OUTPUT(type) ? 1 : CAP_BUFS;

	memset(&req, 0, sizeof(req));
	req.type = type;
	req.memory = V4L2_MEMORY_MMAP;
	req.count = f->nbufs;
	if (ioctl(fd, VIDIOC_REQBUFS, &req) < 0) {
		fprintf(stderr, "%s REQBUFS failed: %m\n", label);
		return -1;
	}
	if (req.count < f->nbufs) {
		fprintf(stderr, "%s got %u buffers, wanted %u\n", label,
			req.count, f->nbufs);
		return -1;
	}

	for (i = 0; i < f->nbufs; i++) {
		memset(&buf, 0, sizeof(buf));
		buf.type = type;
		buf.memory = V4L2_MEMORY_MMAP;
		buf.index = i;
		if (ioctl(fd, VIDIOC_QUERYBUF, &buf) < 0) {
			fprintf(stderr, "%s QUERYBUF %u failed: %m\n", label, i);
			return -1;
		}

		f->length = buf.length;
		f->map[i] = mmap(NULL, buf.length, PROT_READ | PROT_WRITE,
				 MAP_SHARED, fd, buf.m.offset);
		if (f->map[i] == MAP_FAILED) {
			fprintf(stderr, "%s mmap %u failed: %m\n", label, i);
			return -1;
		}
	}

	f->luma.base = f->map[0];
	f->luma.stride = f->bytesperline;

	return 0;
}

/*
 * Paint a flat mid-grey frame with one distinct block in each corner. Chroma is
 * filled neutral for whichever layout the driver picked; the verdict only reads
 * luma, but leaving chroma uninitialised would make a dump hard to look at.
 */
static void paint_source(struct frame *f)
{
	unsigned int x, y;
	unsigned int i;
	unsigned char *chroma = f->map[0] + f->bytesperline * f->height;
	unsigned int chroma_bytes = f->sizeimage - f->bytesperline * f->height;

	for (y = 0; y < f->height; y++)
		memset(f->luma.base + y * f->luma.stride, 128, f->width);

	/*
	 * NV12 chroma is interleaved U,V. Giving U and V different constants
	 * makes the output layout self-describing: read back as I420 the U
	 * plane is all 0x40 and the V plane all 0xC0, read back as NV12 the
	 * same bytes alternate. That is what settles the spec-vs-vendor
	 * disagreement about whether YUV output is always planar.
	 */
	for (i = 0; i < chroma_bytes; i += 2) {
		/*
		 * U carries the chroma row index, so the readback also reveals
		 * which stride the hardware used for the interleaved plane --
		 * the driver programs OUT_PITCH1 assuming I420 (bpl/2), while
		 * interleaved UV needs a full bpl per row.
		 */
		chroma[i] = (i / (f->bytesperline ? f->bytesperline : 1)) & 0x3f;
		chroma[i + 1] = 0xC0;		/* V */
	}

	for (i = 0; i < 4; i++) {
		unsigned int x0 = (i & 1) ? f->width - BLK : 0;
		unsigned int y0 = (i & 2) ? f->height - BLK : 0;

		for (y = y0; y < y0 + BLK; y++)
			for (x = x0; x < x0 + BLK; x++)
				f->luma.base[y * f->luma.stride + x] =
					corner_val[i];
	}
}

/* mean of the inner 16x16 of a corner block, so edge resampling cannot skew it */
static double corner_mean(struct frame *f, int idx)
{
	unsigned int x0 = (idx & 1) ? f->width - BLK : 0;
	unsigned int y0 = (idx & 2) ? f->height - BLK : 0;
	unsigned int x, y;
	double s = 0;

	for (y = y0 + 8; y < y0 + 24; y++)
		for (x = x0 + 8; x < x0 + 24; x++)
			s += f->luma.base[y * f->luma.stride + x];

	return s / 256.0;
}

/* which source corner ended up here, or -1 */
static int classify(double v)
{
	int i;

	for (i = 0; i < 4; i++)
		if (v >= corner_val[i] - 8.0 && v <= corner_val[i] + 8.0)
			return i;
	return -1;
}

/*
 * perm[dst] = src. Named against how the four corners move, so the answer does
 * not depend on trusting the register field's documented direction.
 */
static const char *verdict(const int *perm)
{
	/* dst order is TL, TR, BL, BR */
	static const struct {
		int p[4];
		const char *name;
	} known[] = {
		{ { 0, 1, 2, 3 }, "IDENTITY" },
		{ { 1, 0, 3, 2 }, "H-MIRROR" },
		{ { 2, 3, 0, 1 }, "V-MIRROR" },
		{ { 3, 2, 1, 0 }, "ROT180" },
		/* clockwise 90: TL->TR, TR->BR, BR->BL, BL->TL */
		{ { 2, 0, 3, 1 }, "ROT90_CW" },
		/* counter-clockwise 90: TL->BL, BL->BR, BR->TR, TR->TL */
		{ { 1, 3, 0, 2 }, "ROT90_CCW" },
		/* clockwise 90 then H mirror, and its mirror image */
		{ { 0, 2, 1, 3 }, "TRANSPOSE" },
		{ { 3, 1, 2, 0 }, "ANTITRANSPOSE" },
	};
	unsigned int i;

	for (i = 0; i < sizeof(known) / sizeof(known[0]); i++)
		if (!memcmp(perm, known[i].p, sizeof(known[i].p)))
			return known[i].name;

	return "UNKNOWN";
}

int main(int argc, char **argv)
{
	int angle = argc > 1 ? atoi(argv[1]) : 0;
	int hflip = argc > 2 ? atoi(argv[2]) : 0;
	int vflip = argc > 3 ? atoi(argv[3]) : 0;
	const char *dumpfile = argc > 4 ? argv[4] : NULL;
	struct frame src, dst;
	struct v4l2_buffer buf;
	struct pollfd pfd;
	char path[32], cc[5];
	unsigned int cap_w, cap_h;
	int perm[4], i, fd, type, rc;

	memset(&src, 0, sizeof(src));
	memset(&dst, 0, sizeof(dst));

	fd = find_device(path, sizeof(path));
	if (fd < 0)
		return 1;

	enum_formats(fd, V4L2_BUF_TYPE_VIDEO_OUTPUT, "OUTPUT fmts");
	enum_formats(fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, "CAPTURE fmts");

	printf("\nrequest: rotate=%d hflip=%d vflip=%d\n", angle, hflip, vflip);

	/*
	 * Controls first: the driver recomputes the capture format inside
	 * S_CTRL(V4L2_CID_ROTATE), and refuses to once buffers are allocated.
	 */
	if (set_ctrl(fd, V4L2_CID_ROTATE, angle, "ROTATE") ||
	    set_ctrl(fd, V4L2_CID_HFLIP, hflip, "HFLIP") ||
	    set_ctrl(fd, V4L2_CID_VFLIP, vflip, "VFLIP"))
		return 1;

	if (setup_side(fd, V4L2_BUF_TYPE_VIDEO_OUTPUT, SRC_W, SRC_H, &src,
		       "OUTPUT"))
		return 1;

	cap_w = (angle == 90 || angle == 270) ? SRC_H : SRC_W;
	cap_h = (angle == 90 || angle == 270) ? SRC_W : SRC_H;
	if (setup_side(fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, cap_w, cap_h, &dst,
		       "CAPTURE"))
		return 1;

	fourcc(cc, dst.pixfmt);
	printf("\ncapture came back as %s -- %s\n", cc,
	       dst.pixfmt == V4L2_PIX_FMT_NV12 ?
		       "semi-planar survived, vendor g2d_rotate.c was right" :
		       "planar, matching DE2.0 Spec 5.13.4");

	paint_source(&src);
	for (i = 0; i < (int)dst.nbufs; i++)
		memset(dst.map[i], 0xAA, dst.length);

	memset(&buf, 0, sizeof(buf));
	buf.type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
	buf.memory = V4L2_MEMORY_MMAP;
	buf.index = 0;
	buf.bytesused = src.sizeimage;
	if (ioctl(fd, VIDIOC_QBUF, &buf) < 0) {
		fprintf(stderr, "QBUF OUTPUT failed: %m\n");
		return 1;
	}

	for (i = 0; i < (int)dst.nbufs; i++) {
		memset(&buf, 0, sizeof(buf));
		buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
		buf.memory = V4L2_MEMORY_MMAP;
		buf.index = i;
		if (ioctl(fd, VIDIOC_QBUF, &buf) < 0) {
			fprintf(stderr, "QBUF CAPTURE %d failed: %m\n", i);
			return 1;
		}
	}

	/*
	 * STREAMON on the output queue is what takes the module out of reset --
	 * everything before this point leaves the hardware untouched.
	 */
	type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
	if (ioctl(fd, VIDIOC_STREAMON, &type) < 0) {
		fprintf(stderr, "STREAMON OUTPUT failed: %m\n");
		return 1;
	}
	type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	if (ioctl(fd, VIDIOC_STREAMON, &type) < 0) {
		fprintf(stderr, "STREAMON CAPTURE failed: %m\n");
		return 1;
	}

	pfd.fd = fd;
	pfd.events = POLLIN;
	rc = poll(&pfd, 1, 3000);
	if (rc <= 0) {
		printf("VERDICT=HANG (no completion in 3s; irq lost or engine stuck)\n");
		return 2;
	}

	memset(&buf, 0, sizeof(buf));
	buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	buf.memory = V4L2_MEMORY_MMAP;
	if (ioctl(fd, VIDIOC_DQBUF, &buf) < 0) {
		fprintf(stderr, "DQBUF CAPTURE failed: %m\n");
		return 2;
	}
	if (buf.flags & V4L2_BUF_FLAG_ERROR) {
		printf("VERDICT=ERROR (hardware flagged the buffer)\n");
		return 2;
	}

	/* read back whichever buffer the hardware actually filled */
	dst.luma.base = dst.map[buf.index];

	printf("\ncorners (dst <- src):");
	for (i = 0; i < 4; i++) {
		double m = corner_mean(&dst, i);

		perm[i] = classify(m);
		printf(" %s<-%s(%.0f)", corner_name[i],
		       perm[i] < 0 ? "??" : corner_name[perm[i]], m);
	}
	printf("\n");

	for (i = 0; i < 4; i++)
		if (perm[i] < 0) {
			printf("VERDICT=GARBAGE\n");
			break;
		}
	if (i == 4)
		printf("VERDICT=%s\n", verdict(perm));

	/*
	 * What the hardware actually wrote into the chroma area, regardless of
	 * what the driver declared the capture format to be.
	 */
	{
		unsigned char *c = dst.luma.base +
				   dst.bytesperline * dst.height;
		unsigned int uplane = dst.bytesperline * dst.height / 4;
		/*
		 * U carries a row index and V a constant, so interleaved shows
		 * up as every odd byte being 0xC0 while the even ones agree,
		 * and planar as a run of equal U bytes with the V constant only
		 * appearing a quarter-plane later.
		 */
		int alt = (c[1] == 0xC0 && c[3] == 0xC0 && c[0] == c[2] &&
			   c[0] != 0xC0);
		int planar = (c[0] == c[1] && c[1] == c[2] &&
			      c[uplane] == 0xC0 && c[uplane + 1] == 0xC0);

		printf("chroma head:");
		for (i = 0; i < 8; i++)
			printf(" %02x", c[i]);
		printf("   at U+%u:", uplane);
		for (i = 0; i < 4; i++)
			printf(" %02x", c[uplane + i]);
		printf("\nCHROMA=%s\n", alt ? "NV12_INTERLEAVED (vendor g2d_rotate.c right, spec wrong)" :
				       planar ? "I420_PLANAR (DE2.0 Spec 5.13.4 right)" :
						"UNRECOGNISED");

		/*
		 * Row index written into U, read back at both candidate
		 * strides. Whichever column counts 0,1,2,3... is the stride the
		 * hardware actually used for the interleaved chroma plane.
		 */
		printf("stride probe  bpl(%u):", dst.bytesperline);
		for (i = 0; i < 6; i++)
			printf(" %02x", c[i * dst.bytesperline]);
		printf("   bpl/2(%u):", dst.bytesperline / 2);
		for (i = 0; i < 6; i++)
			printf(" %02x", c[i * (dst.bytesperline / 2)]);
		printf("\n");
	}

	if (dumpfile) {
		int df = open(dumpfile, O_WRONLY | O_CREAT | O_TRUNC, 0644);

		if (df >= 0) {
			if (write(df, dst.luma.base, dst.sizeimage) < 0)
				perror("write");
			close(df);
			printf("dumped %u bytes to %s\n", dst.sizeimage,
			       dumpfile);
		}
	}

	close(fd);
	return 0;
}
