python ood.py --m baseline --mc /home/ferles/checkpoints/eb0/cifar10/Eb0Cifar10.pth --in cifar10 --val svhn --out stl --nc 10 --dv 6 > results/image_resizing_cifar10_svhn_tiny_baseline.txt
python ood.py --m baseline --mc /home/ferles/checkpoints/eb0/cifar10/Eb0Cifar10.pth --in cifar10 --val svhn --out tinyimagenet --nc 10 --dv 6 > results/image_resizing_cifar10_svhn_stl_baseline.txt
python ood.py --m mahalanobis --mc /home/ferles/checkpoints/eb0/cifar10/Eb0Cifar10.pth --in cifar10 --val svhn --out stl  --nc 10 --dv 6 > results/image_resizing_cifar10_svhn_tiny_mahalanobis.txt
python ood.py --m mahalanobis --mc /home/ferles/checkpoints/eb0/cifar10/Eb0Cifar10.pth --in cifar10 --val svhn --out tinyimagenet --nc 10 --dv 6 > results/image_resizing_cifar10_svhn_tiny_mahalanobis.txt