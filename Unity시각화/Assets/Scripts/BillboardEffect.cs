using UnityEngine;

/// 오브젝트를 항상 카메라를 향하도록 회전시키는 빌보드 효과
public class BillboardEffect : MonoBehaviour
{
    [Header("빌보드 설정")]
    public bool lockYRotation = true; // Y축 회전만 허용 (더 자연스러움)
    public bool useMainCamera = true; // Main Camera 사용 여부

    private Camera targetCamera;

    void Start()
    {
        if (useMainCamera)
        {
            targetCamera = Camera.main;
            if (targetCamera == null)
                targetCamera = FindObjectOfType<Camera>();
        }
    }

    void Update()
    {
        if (targetCamera == null) return;

        Vector3 targetPosition = targetCamera.transform.position;

        if (lockYRotation)
        {
            // Y축만 회전 (지면에 평행하게 유지)
            targetPosition.y = transform.position.y;
            Vector3 direction = (targetPosition - transform.position).normalized;

            if (direction != Vector3.zero)
            {
                transform.rotation = Quaternion.LookRotation(direction);
            }
        }
        else
        {
            // 완전한 빌보드 효과 (카메라 방향으로 완전히 회전)
            Vector3 direction = (targetPosition - transform.position).normalized;
            if (direction != Vector3.zero)
            {
                transform.rotation = Quaternion.LookRotation(direction);
            }
        }
    }
}